'use strict';

const { performSearch } = require('./search');

const DECISION_MODEL = 'openai/gpt-oss-20b';
const MAIN_MODEL = 'openai/gpt-oss-120b';

const DECISION_SYSTEM = 'Is this a casual greeting or small talk (hi, hello, how are you, thanks, bye)? Reply NO. Does the user ask about news, events, facts, or anything time-sensitive that needs current info? Reply YES. If you\'re unsure, default to NO. Reply ONLY \'YES\' or \'NO\'.';

let Groq = null;
try {
  Groq = require('groq-sdk');
} catch (_e) {
  Groq = null;
}

class AIModule {
  constructor(aiConfig) {
    this.config = aiConfig;
    this.history = [];
    this.groq = null;
    this._initClient();
  }

  _initClient() {
    const key = String(this.config.get('api_key') || '').trim();
    if (key && Groq) {
      try {
        this.groq = new Groq({ apiKey: key });
      } catch (_e) {
        this.groq = null;
      }
    } else {
      this.groq = null;
    }
  }

  async getAiResponse(prompt, speakerName) {
    if (!this.groq) {
      return 'Groq API key not set.';
    }
    try {
      const decision = await this.groq.chat.completions.create({
        model: DECISION_MODEL,
        messages: [
          { role: 'system', content: DECISION_SYSTEM },
          { role: 'user', content: prompt },
        ],
        max_completion_tokens: 32,
        temperature: 0,
        reasoning_effort: 'low',
      });
      const needsSearch = String(decision.choices[0].message.content || '').toUpperCase().includes('YES');

      let searchContext = '';
      if (needsSearch) {
        const refiner = await this.groq.chat.completions.create({
          model: DECISION_MODEL,
          messages: [
            { role: 'system', content: 'Create a 3-6 word search query. Only output the query.' },
            { role: 'user', content: prompt },
          ],
          max_completion_tokens: 128,
          temperature: 0,
          reasoning_effort: 'low',
        });
        const query = refiner.choices[0].message.content.trim().replace(/"/g, '');
        searchContext = await performSearch(query);
      }

      const systemInstr = this.config.get('system_instruction');
      const chatterContext = this.config.get('chatter_context') || {};

      const relevant = [];
      if (speakerName && chatterContext[speakerName.toLowerCase()]) {
        relevant.push(`Context for @${speakerName}: ${chatterContext[speakerName.toLowerCase()]}`);
      }

      const promptLower = prompt.toLowerCase();
      for (const [u, info] of Object.entries(chatterContext)) {
        if (speakerName && u === speakerName.toLowerCase()) continue;
        if (promptLower.includes(`@${u}`) || promptLower.includes(u)) {
          relevant.push(`Context for @${u}: ${info}`);
        }
      }

      let finalInstr = systemInstr;
      if (relevant.length) {
        finalInstr += `\n\nCONTEXT:\n${relevant.join('\n')}`;
      }
      if (searchContext) {
        finalInstr += `\n\nSEARCH RESULTS:\n${searchContext}\n\nUse the search results to answer the question if they contain relevant info.`;
      }
      finalInstr += '\n\nBe natural and concise.';

      const messages = [{ role: 'system', content: finalInstr }, ...this.history, { role: 'user', content: prompt }];

      const completion = await this.groq.chat.completions.create({
        model: MAIN_MODEL,
        messages,
        max_completion_tokens: 600,
        temperature: 0.6,
        reasoning_effort: 'low',
      });
      const resp = String(completion.choices[0].message.content || '').trim();

      this.history.push({ role: 'user', content: prompt });
      this.history.push({ role: 'assistant', content: resp });
      if (this.history.length > 10) {
        this.history = this.history.slice(-10);
      }

      return resp;
    } catch (e) {
      const msg = String(e.message || e).slice(0, 60);
      return `AI Error: ${msg}...`;
    }
  }
}

module.exports = { AIModule, DECISION_MODEL, MAIN_MODEL };
