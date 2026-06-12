// src/rag/rag.js
// ═══════════════════════════════════════════
// HYBRID RAG RETRIEVAL LIBRARY
// Pure JS · No dependencies · Browser-ready
// BM25 + phonetic + levenshtein + n-gram + sentence-window context.
// ═══════════════════════════════════════════

// ─────────────────────────────────────────
// TextProcessor — normalization, sentence splitting, tokenization
// ─────────────────────────────────────────
class TextProcessor {
  static normalize(text) {
    return text
      .toLowerCase()
      .replace(/[^\w\s]/g, "")
      .split(/\s+/)
      .filter((w) => w.length > 2);
  }

  static splitSentences(text) {
    return text
      .replace(/\n/g, " ")
      .split(/[.!?]+/)
      .map((s) => s.trim())
      .filter((s) => s.length > 0);
  }
}

// ─────────────────────────────────────────
// Similarity — phonetic, levenshtein, n-gram
// ─────────────────────────────────────────
class Similarity {
  static phonetic(word) {
    word = word.toLowerCase();
    return word
      .replace(/ph/g, "f")
      .replace(/ee/g, "i")
      .replace(/ea/g, "i")
      .replace(/oo/g, "u")
      .replace(/ou/g, "u")
      .replace(/ck/g, "k")
      .replace(/c/g, "k")
      .replace(/z/g, "s")
      .replace(/x/g, "ks");
  }

  static levenshtein(a, b) {
    const matrix = [];
    for (let i = 0; i <= b.length; i++) matrix[i] = [i];
    for (let j = 0; j <= a.length; j++) matrix[0][j] = j;

    for (let i = 1; i <= b.length; i++) {
      for (let j = 1; j <= a.length; j++) {
        if (b[i - 1] === a[j - 1]) matrix[i][j] = matrix[i - 1][j - 1];
        else
          matrix[i][j] = Math.min(
            matrix[i - 1][j - 1] + 1,
            matrix[i][j - 1] + 1,
            matrix[i - 1][j] + 1
          );
      }
    }
    return matrix[b.length][a.length];
  }

  static ngrams(str, n = 3) {
    const grams = [];
    for (let i = 0; i <= str.length - n; i++) grams.push(str.substring(i, i + n));
    return grams;
  }

  static ngramSimilarity(a, b) {
    const g1 = this.ngrams(a);
    const g2 = this.ngrams(b);
    const set2 = new Set(g2);
    let matches = 0;
    g1.forEach((g) => {
      if (set2.has(g)) matches++;
    });
    return matches / Math.max(g1.length, g2.length, 1);
  }
}

// ─────────────────────────────────────────
// IndexBuilder — inverted index + document frequency
// ─────────────────────────────────────────
class IndexBuilder {
  constructor() {
    this.sentences = [];
    this.index = {};
    this.df = {};
    this.docs = [];
  }

  build(text) {
    this.sentences = TextProcessor.splitSentences(text);
    this.index = {};
    this.df = {};
    this.docs = [];

    this.sentences.forEach((sentence, id) => {
      const words = TextProcessor.normalize(sentence);
      this.docs[id] = words;
      const unique = [...new Set(words)];

      unique.forEach((w) => {
        if (!this.index[w]) this.index[w] = [];
        this.index[w].push(id);
        this.df[w] = (this.df[w] || 0) + 1;
      });
    });
  }
}

// ─────────────────────────────────────────
// Ranker — BM25 + hybrid scoring
// ─────────────────────────────────────────
class Ranker {
  static bm25(queryWords, words, df, N) {
    let score = 0;
    queryWords.forEach((q) => {
      const tf = words.filter((w) => w === q).length;
      if (tf > 0) {
        const idf = Math.log((N + 1) / (df[q] || 1));
        score += tf * idf * 2;
      }
    });
    return score;
  }

  static hybrid(queryWords, sentenceWords, sentence, df, N) {
    let score = this.bm25(queryWords, sentenceWords, df, N);

    queryWords.forEach((q) => {
      sentenceWords.forEach((w) => {
        const pw = Similarity.phonetic(w);
        const pq = Similarity.phonetic(q);

        if (Similarity.levenshtein(pw, pq) <= 1) score += 0.7;

        const sim = Similarity.ngramSimilarity(pw, pq);
        if (sim > 0.5) score += sim;
      });
    });

    if (sentence.toLowerCase().includes(queryWords.join(" "))) score += 4;

    return score;
  }
}

// ─────────────────────────────────────────
// Retriever — candidate search + ranking
// ─────────────────────────────────────────
class Retriever {
  constructor(indexBuilder) {
    this.index = indexBuilder.index;
    this.docs = indexBuilder.docs;
    this.df = indexBuilder.df;
    this.sentences = indexBuilder.sentences;
  }

  search(query) {
    const queryWords = TextProcessor.normalize(query);
    const candidates = new Set();

    queryWords.forEach((w) => {
      (this.index[w] || []).forEach((id) => candidates.add(id));
    });

    // Also add fuzzy candidates via phonetic matching
    queryWords.forEach((q) => {
      const pq = Similarity.phonetic(q);
      Object.keys(this.index).forEach((w) => {
        const pw = Similarity.phonetic(w);
        if (Similarity.levenshtein(pw, pq) <= 1) {
          this.index[w].forEach((id) => candidates.add(id));
        }
      });
    });

    const scored = [];
    candidates.forEach((id) => {
      const words = this.docs[id];
      const sentence = this.sentences[id];
      const score = Ranker.hybrid(queryWords, words, sentence, this.df, this.sentences.length);
      if (score > 0) scored.push({ id, score, sentence });
    });

    scored.sort((a, b) => b.score - a.score);
    return scored;
  }
}

// ─────────────────────────────────────────
// ContextBuilder — sentence window extraction
// ─────────────────────────────────────────
class ContextBuilder {
  static window(sentences, id, size = 1) {
    const start = Math.max(0, id - size);
    const end = Math.min(sentences.length, id + size + 1);
    return sentences.slice(start, end).join(". ");
  }
}

// ─────────────────────────────────────────
// HybridRAG — main engine
// ─────────────────────────────────────────
export class HybridRAG {
  constructor() {
    this.indexBuilder = new IndexBuilder();
    this.retriever = null;
    this.indexed = false;
    this.sourceCount = 0;
    this.sentenceCount = 0;
  }

  index(text) {
    this.indexBuilder.build(text);
    this.retriever = new Retriever(this.indexBuilder);
    this.indexed = true;
    this.sourceCount++;
    this.sentenceCount = this.indexBuilder.sentences.length;
    return {
      sentences: this.sentenceCount,
      uniqueTerms: Object.keys(this.indexBuilder.index).length,
    };
  }

  addText(text) {
    const existingSentences = this.indexBuilder.sentences.join(". ");
    const combined = existingSentences ? existingSentences + ". " + text : text;
    return this.index(combined);
  }

  query(query, topK = 5, windowSize = 1) {
    if (!this.indexed || !this.retriever) {
      return { passages: [], prompt: "", ranked: [], error: "No text indexed yet." };
    }

    const ranked = this.retriever.search(query);
    const passages = [];
    const seen = new Set();

    ranked.slice(0, topK).forEach((r) => {
      const ctx = ContextBuilder.window(this.indexBuilder.sentences, r.id, windowSize);
      if (!seen.has(ctx)) {
        seen.add(ctx);
        passages.push({ text: ctx, score: r.score, sentenceId: r.id, original: r.sentence });
      }
    });

    const prompt =
      "Use the following context to answer the question:\n\n" +
      passages.map((p, i) => `[${i + 1}] (score: ${p.score.toFixed(2)}) ${p.text}`).join("\n\n") +
      "\n\nQuestion: " + query +
      "\nAnswer:";

    return { passages, prompt, ranked: ranked.slice(0, topK), totalCandidates: ranked.length };
  }

  getStats() {
    return {
      indexed: this.indexed,
      sentences: this.sentenceCount,
      uniqueTerms: Object.keys(this.indexBuilder.index).length,
      sources: this.sourceCount,
    };
  }

  clear() {
    this.indexBuilder = new IndexBuilder();
    this.retriever = null;
    this.indexed = false;
    this.sourceCount = 0;
    this.sentenceCount = 0;
  }
}

// ═══════════════════════════════════════════
// Browser-persistent wrapper (localStorage) exposing the agent tool API.
// Raw source texts are stored so the index survives page reloads.
// ═══════════════════════════════════════════
const STORE_KEY = "hearthnet_rag_sources";
const engine = new HybridRAG();

function loadSources() {
  try {
    return JSON.parse(localStorage.getItem(STORE_KEY) || "[]");
  } catch {
    return [];
  }
}

function rebuild(sources) {
  engine.clear();
  const combined = sources.map((s) => s.text).join(". ");
  if (combined.trim()) engine.index(combined);
}

// Rebuild on module load so prior knowledge persists.
rebuild(loadSources());

export function ragIndex(text, source = "manual") {
  const sources = loadSources();
  sources.push({ text: String(text), source, ts: Date.now() });
  localStorage.setItem(STORE_KEY, JSON.stringify(sources));
  const stats = engine.addText(String(text));
  return `indexed "${source}" — ${stats.sentences} sentence(s), ${stats.uniqueTerms} terms`;
}

export function ragSearch(query, topK = 4) {
  const res = engine.query(query, topK, 1);
  if (res.error) return res.error;
  if (!res.passages.length) return "no relevant passages found";
  return res.passages.map((p, i) => `[${i + 1}] (score ${p.score.toFixed(2)}) ${p.text}`).join("\n\n");
}

export function ragStats() {
  return engine.getStats();
}

export function ragClear() {
  localStorage.removeItem(STORE_KEY);
  engine.clear();
  return "knowledge base cleared";
}
