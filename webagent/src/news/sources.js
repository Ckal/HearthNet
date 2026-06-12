// src/news/sources.js
// Curated RSS/Atom feeds. Static array — no backend required.

export const RSS_SOURCES = [
  { name: "BBC World", cat: "world", url: "https://feeds.bbci.co.uk/news/world/rss.xml" },
  { name: "BBC Top", cat: "world", url: "https://feeds.bbci.co.uk/news/rss.xml" },
  { name: "Reuters World", cat: "world", url: "https://news.google.com/rss/search?q=when:24h+allinurl:reuters.com&ceid=US:en&hl=en-US&gl=US" },
  { name: "AP Top News", cat: "world", url: "https://news.google.com/rss/search?q=when:24h+allinurl:apnews.com&ceid=US:en&hl=en-US&gl=US" },
  { name: "Al Jazeera", cat: "world", url: "https://www.aljazeera.com/xml/rss/all.xml" },
  { name: "DW Top Stories", cat: "world", url: "https://rss.dw.com/rdf/rss-en-top" },
  { name: "France 24", cat: "world", url: "https://www.france24.com/en/rss" },
  { name: "Hacker News", cat: "tech", url: "https://news.ycombinator.com/rss" },
  { name: "The Hacker News", cat: "cyber", url: "https://thehackernews.com/rss.xml" },
  { name: "Krebs", cat: "cyber", url: "https://krebsonsecurity.com/feed/" },
  { name: "BleepingComputer", cat: "cyber", url: "https://www.bleepingcomputer.com/feed/" },
  { name: "NASA", cat: "space", url: "https://www.nasa.gov/rss/dyn/breaking_news.rss" },
  { name: "NOAA Alerts", cat: "weather", url: "https://alerts.weather.gov/cap/us.php?x=0" },
  { name: "USGS Earthquakes", cat: "earth", url: "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/all_hour.atom" },
];
