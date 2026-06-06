import threading

from groq import Groq

try:
    from ddgs import DDGS
except ImportError:
    DDGS = None


class AIModule:
    def __init__(self, config):
        self.config = config
        self.groq_client = None
        self.history = []
        self.history_lock = threading.RLock()
        self._init_client()

    def _init_client(self):
        key = self.config["api_key"].strip()
        if key:
            try:
                self.groq_client = Groq(api_key=key)
            except Exception:
                self.groq_client = None
        else:
            self.groq_client = None

    def perform_search(self, query: str, max_results: int = 5) -> str:
        if DDGS is None:
            return "Web search not available (ddgs not installed)."
        try:
            with DDGS() as ddgs:
                results = list(ddgs.text(query, max_results=max_results))
                if not results:
                    return "No search results found."
                seen = set()
                filtered = []
                for r in results:
                    title = r.get('title', '')
                    body = r.get('body', '')
                    url = r.get('href', r.get('url', ''))
                    key = (title.lower().strip(), body.lower().strip())
                    if key in seen:
                        continue
                    seen.add(key)
                    text = (title + " " + body).lower()
                    if any(w in url.lower() for w in ['crazygames', 'worldguessr', 'openguessr', 'geoguesser-free']):
                        continue
                    filtered.append(f"Result: {title}\nContent: {body}")
                if not filtered:
                    return "No search results found."
                return "\n\n".join(filtered)
        except Exception as e:
            return f"Search Error: {e}"

    def get_ai_response(self, prompt: str, speaker_name: str = None) -> str | None:
        if not self.config["enabled"]:
            return None
        if self.groq_client is None:
            return "Groq API key not set."

        try:
            decision = self.groq_client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=[
                    {"role": "system",
                     "content": "Is this a casual greeting or small talk (hi, hello, how are you, thanks, bye)? Reply NO. Does the user ask about news, events, facts, or anything time-sensitive that needs current info? Reply YES. If you're unsure, default to NO. Reply ONLY 'YES' or 'NO'."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=5,
                temperature=0.0
            )
            needs_search = "YES" in decision.choices[0].message.content.upper()

            search_context = ""
            if needs_search:
                refiner = self.groq_client.chat.completions.create(
                    model="llama-3.1-8b-instant",
                    messages=[
                        {"role": "system", "content": "Create a 3-6 word search query. Only output the query."},
                        {"role": "user", "content": prompt}
                    ],
                    max_tokens=64,
                    temperature=0.0
                )
                query = refiner.choices[0].message.content.strip().replace('"', '')
                search_context = self.perform_search(query)

            system_instr = self.config["system_instruction"]
            chatter_context = self.config.get("chatter_context", {})

            relevant = []
            if speaker_name and speaker_name.lower() in chatter_context:
                relevant.append(f"Context for @{speaker_name}: {chatter_context[speaker_name.lower()]}")

            p_low = prompt.lower()
            for u, info in chatter_context.items():
                if speaker_name and u == speaker_name.lower():
                    continue
                if f"@{u}" in p_low or u in p_low:
                    relevant.append(f"Context for @{u}: {info}")

            final_instr = system_instr
            if relevant:
                final_instr += "\n\nCONTEXT:\n" + "\n".join(relevant)
            if search_context:
                final_instr += f"\n\nSEARCH RESULTS:\n{search_context}\n\nUse the search results to answer the question if they contain relevant info."
            final_instr += "\n\nBe natural and concise."

            messages = [{"role": "system", "content": final_instr}]
            with self.history_lock:
                messages.extend(self.history)
            messages.append({"role": "user", "content": prompt})

            completion = self.groq_client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=messages,
                max_tokens=300,
                temperature=0.6
            )
            resp = completion.choices[0].message.content.strip()

            with self.history_lock:
                self.history.append({"role": "user", "content": prompt})
                self.history.append({"role": "assistant", "content": resp})
                if len(self.history) > 10:
                    self.history = self.history[-10:]

            return resp

        except Exception as e:
            return f"AI Error: {str(e)[:60]}..."
