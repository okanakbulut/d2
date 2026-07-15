import { defineCollection } from 'astro:content';
import { glob } from 'astro/loaders';
import { docsSchema } from '@astrojs/starlight/schema';

export const collections = {
	// Load the doc-tested markdown from the repo-level docs/ directory so it
	// stays the single source of truth (pytest runs its examples as doctests).
	docs: defineCollection({
		loader: glob({ pattern: '**/[^_]*.md', base: '../docs' }),
		schema: docsSchema(),
	}),
};
