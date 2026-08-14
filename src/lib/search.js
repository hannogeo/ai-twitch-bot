'use strict';

let ddgsSearch = null;
try {
  const ddgs = require('duck-duck-scrape');
  ddgsSearch = ddgs.search;
} catch (_e) {
  ddgsSearch = null;
}

const BLOCKED_DOMAINS = ['crazygames', 'worldguessr', 'openguessr', 'geoguesser-free'];

async function performSearch(query, maxResults = 5) {
  if (!ddgsSearch) {
    return 'Web search not available (duck-duck-scrape not installed).';
  }
  try {
    const results = await ddgsSearch(query);
    if (!results || !results.length) {
      return 'No search results found.';
    }
    const seen = new Set();
    const filtered = [];
    for (const r of results.slice(0, maxResults * 2)) {
      const title = r.title || '';
      const body = r.description || '';
      const url = r.url || '';
      const key = `${title.toLowerCase().trim()}|${body.toLowerCase().trim()}`;
      if (seen.has(key)) continue;
      seen.add(key);
      const lowerUrl = url.toLowerCase();
      if (BLOCKED_DOMAINS.some((w) => lowerUrl.includes(w))) continue;
      filtered.push(`Result: ${title}\nContent: ${body}`);
      if (filtered.length >= maxResults) break;
    }
    if (!filtered.length) {
      return 'No search results found.';
    }
    return filtered.join('\n\n');
  } catch (e) {
    return `Search Error: ${e.message || e}`;
  }
}

module.exports = { performSearch };
