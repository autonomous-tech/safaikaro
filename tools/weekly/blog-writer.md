# Blog and page writer brief

Load this before writing or rewriting any blog post or service page for safaikaro.pk. It is the whole standard: research, structure, voice, CTAs, schema, and the critic checklist. A post that skips a step here is dropped, not fixed later.

## 0. What a SafaiKaro post is for

A Karachi homeowner or office manager typed something into Google, often in Roman Urdu, sometimes in Urdu script, sometimes half English. They want the answer first, then to know what it costs and whether SafaiKaro can come this week. The post earns trust by answering completely and specifically, then hands the reader to WhatsApp. It is written by people who do this work every day, and it reads like it.

## 1. Research, before a single line of copy

Do all of it and keep notes in `tools/weekly/output/research-<slug>.md` (gitignored). Every factual claim in the post traces to one of these.

1. **Query set (Search Console).** From `report_data.gsc`: the seed query, every variant in `top_queries_28d`, `new_queries`, `striking_distance` and `low_ctr` that shares the intent, with impressions and current position. Include Roman-Urdu and Urdu-script spellings (khatmal, کھٹمل, khutmal, bed bug). This is the vocabulary the post must use verbatim.
2. **Keyword universe (Ahrefs).** `keywords-explorer/overview` and `matching-terms` for the seed, country pk: volume, difficulty, parent topic, related questions. Pick the parent topic the post owns and the 5 to 12 secondary phrases it must cover. Note KD; anything above 20 needs a genuinely better page, not a similar one.
3. **SERP study.** Fetch the top 8 results for the seed query (Pakistan, mobile). For each: what the page answers, what it misses, word count, whether it shows a price, whether it names areas, what format Google rewards (list, table, definition, video). The post has to be the most complete and most specific of the eight, not the longest.
4. **People's questions.** Reddit (r/pakistan, r/karachi), Facebook group threads if fetchable, YouTube comments on Urdu pest videos, the site's own `faq_open` events from PostHog, and the WhatsApp questions the founder has already answered on existing pages. Quote real phrasing where it is public; never invent a quote.
5. **Facts and mechanism.** What actually works and why: chemistry class, dwell time, why DIY fails, seasonality in Karachi (monsoon cockroaches, winter termite swarms, summer bed bugs, September to November dengue), building types (flats vs bungalows vs offices). Cross-check with two independent sources, prefer WHO, CDC, university extension pages, manufacturer labels. Never cite a licence, certificate or membership SafaiKaro does not hold.
6. **Internal map.** Which service page, area pages and existing posts this one links to and from. Every post links to exactly one service page as its money path, to the price list, and to two related posts. Two existing pages get a link back to the new post in the same PR.
7. **Prices.** Only values that exist in `prices.js`, rendered with `data-price` spans. If the service has no price row, the post says "quote on WhatsApp" and never invents a number.

## 2. Structure

Order matters. The reader is on a phone, mid-problem.

1. **Title (55 to 62 characters).** Exact phrase first, then the promise. Roman Urdu with the English term in brackets when the query is bilingual. A month and year only on price or cost posts (then it is refreshed monthly).
2. **Answer block, first 60 words.** The direct answer to the query in two or three plain sentences. Quotable on its own, no preamble, no "in this guide". This is what Google, Bing and AI answer engines lift. For a definition query it is the definition; for a cost query it is the range with the Rs anchor; for a how-to it is the one-line method.
3. **At a glance.** A 4 to 6 row table or list: cost, time, sessions, guarantee, prep, areas served. Numbers only from `prices.js` and known ops facts.
4. **Body, 900 to 1,800 words**, in H2 sections named the way people ask (the query variants from research become the headings). Each section opens with its answer, then the reasoning, then a Karachi-specific detail (building type, area, season, water and humidity, neighbour infestations).
5. **What DIY gets you.** Honest. What sprays and home remedies do and do not do, with the mechanism. This is the section competitors skip and the one readers trust.
6. **What SafaiKaro does.** Process in numbered steps, chemicals class, dwell time, sessions, the 90-day guarantee, what the customer prepares. Same-day only for DHA, Clifton, PECHS, Bahadurabad and Saddar; other districts say "next available slot".
7. **Bridge to the service page.** One paragraph that sends the reader with a problem to the matching service page, linked on the phrase they searched.
8. **FAQ, 5 to 8 pairs.** Questions in the reader's words (from research step 4). Answers 30 to 70 words, self-contained. The same pairs go in the FAQPage schema, character for character.
9. **Author box.** "Written by the SafaiKaro team" with the neutral bio from the site, no certification or registration claims.
10. **Closing CTA.** Repeat the price anchor and the WhatsApp prefill for this exact service.

## 3. CTAs

- One WhatsApp CTA after the answer block, one mid-body after the "what SafaiKaro does" section, one at the close. All three use the site's `wa.me` link with a prefill naming the service and, when the post is area-specific, the area: `Hi SafaiKaro, I need {service} in {area} Karachi`. The delegated listener in `prices.js` tags them automatically; add `data-cta="inline-answer|inline-process|footer"` on the anchors.
- One `tel:` link in the mid-body CTA for readers who call.
- CTA copy is specific and calm: "WhatsApp karein, aaj hi slot confirm hoga" beats "Contact us now". No urgency theatre, no fake countdowns.
- A price anchor sits within one screen of every CTA.

## 4. AEO and GEO

- The answer block and every FAQ answer must make sense with no other context: a sentence a search engine or an AI assistant can quote and attribute.
- Use the entity names consistently: pest name in English, Roman Urdu and Urdu script once each near the top, then one form throughout.
- Define terms the first time they appear (fumigation vs spray vs gel bait vs heat treatment).
- Include a "How much does it cost" H2 with the Rs anchor and what changes the price (size, infestation level, sessions). Cost questions are the most quoted.
- Structured data: `BlogPosting` (headline, datePublished, dateModified, author as Organization) and `FAQPage` with the exact on-page pairs. Breadcrumb list. No `aggregateRating`, no review counts.
- `tools/generate-seo-files.py` adds the post to sitemap.xml and llms.txt; the llms.txt narrative for the topic is refreshed through `tools/llms-narrative-template.md` when the post changes what SafaiKaro says about that pest.
- Internal links use the query phrase as anchor text, never "click here".

## 5. Voice

Roman Urdu as spoken in Karachi, with English technical terms where people actually use them. Short sentences mixed with a few longer ones. Second person. Concrete over general.

Write like the technician who was in the flat yesterday:

- Say what happens: "Spray ke baad 4 ghante ghar band rehta hai, phir windows kholein" rather than "Ensure proper ventilation after treatment."
- Use the reader's words for the problem before the technical term.
- One idea per paragraph, three to five sentences, then a break.
- Numbers are specific: sessions, days, hours, Rs, square yards.
- Admit limits: what cannot be guaranteed, when a second visit is normal, when a landlord has to be involved.

Never:

- Em-dashes (use a comma, a full stop or a colon).
- Openers like "In today's world", "When it comes to", "It is important to note", "Let's dive in", "In conclusion".
- Triads for rhythm ("fast, safe and effective"), rhetorical questions in a row, "not only ... but also".
- Words that sell instead of inform: "premium", "state-of-the-art", "hassle-free", "peace of mind", "best in Karachi".
- Claims of licences, certifications, registrations, memberships, review counts, years in business, homes served.
- Restaurants, cafes, food service, hotels as customers (founder ruled them out).
- Same-day promises outside DHA, Clifton, PECHS, Bahadurabad, Saddar.
- A termite guarantee other than "90-day" until the founder decides.
- Generic stock phrasing that could sit on any pest site in any city. If a paragraph does not mention something specific to Karachi, this pest, or this method, rewrite or cut it.

## 6. Critic checklist (run as a hostile reader, fix once, drop on second fail)

1. Does the first 60 words answer the query without preamble? Read it aloud.
2. Are the query variants from research present as headings or first sentences, verbatim?
3. Every number: traceable to `prices.js` or the research notes? Any Rs value not in `prices.js` fails lint anyway.
4. Any banned phrase from `config.json`, any licence or certification wording, any em-dash? Fail.
5. Would a Karachi operator read a sentence and say "that is not how it works here"? Geography (blocks, phases, areas), seasons, building types, water, humidity.
6. Does it sound like a person? Vary sentence length, cut every sentence that only exists for rhythm, cut every adjective that is not doing work. If three consecutive paragraphs open the same way, rewrite.
7. FAQ pairs identical on page and in schema? Author box neutral? PostHog snippet and `prices.js` loaded? Internal links present in both directions?
8. Would you send this to the founder to post on the SafaiKaro WhatsApp broadcast as is? If not, it is not done.
