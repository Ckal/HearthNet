// src/agent/tools.js
// Thin adapters that map the agent's tool-call shape to concrete browser deps.

export function createTools({ webSearch, scrape, summarize, remember, schedule, ragindex, ragsearch }) {
  return {
    websearch: async ({ query }) => webSearch(query),
    scrape: async ({ url }) => scrape(url),
    summarize: async ({ text, focus }) => summarize(text, focus),
    remember: async ({ content }) => remember(content),
    schedule: async ({ delaySec, message }) => schedule(delaySec, message),
    ragindex: async ({ text, source }) => ragindex(text, source),
    ragsearch: async ({ query, topK }) => ragsearch(query, topK),
  };
}
