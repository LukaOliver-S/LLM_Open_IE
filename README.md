# LLM_Open_IE

A pipeline for Open Information Extraction (Open IE) in Portuguese using large language models. Given a sentence, it extracts relational triples ⟨ARG1, REL, ARG2⟩ that encode the factual propositions expressed in the text, without relying on predefined domains or ontologies.

The extraction is guided by explicit structural and semantic rules (grounded in the OIEC-PT, DPTO-IE and Abstractive-Bruno annotation methodology), so the LLM produces triples that stay faithful to the sentence rather than inventing facts. The pipeline runs sentences through rule-encoded prompts, parses the model's output into structured triples, and validates them against the rules.
