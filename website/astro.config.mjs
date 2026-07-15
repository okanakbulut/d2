// @ts-check
import { defineConfig } from 'astro/config';
import starlight from '@astrojs/starlight';
import starlightLlmsTxt from 'starlight-llms-txt';
import remarkMdLinks from './src/plugins/remark-md-links.mjs';

// https://astro.build/config
export default defineConfig({
	site: 'https://okanakbulut.github.io',
	base: '/norm',
	markdown: {
		remarkPlugins: [remarkMdLinks],
	},
	integrations: [
		starlight({
			title: 'Norm',
			description: 'Async-first PostgreSQL ORM for Python',
			social: [
				{ icon: 'github', label: 'GitHub', href: 'https://github.com/okanakbulut/norm' },
			],
			editLink: {
				baseUrl: 'https://github.com/okanakbulut/norm/edit/main/docs/',
			},
			plugins: [starlightLlmsTxt()],
			sidebar: [
				{
					label: 'Start Here',
					items: [
						{ label: 'Overview', link: '/' },
						{ label: 'Getting Started', slug: 'getting-started' },
					],
				},
				{
					label: 'Guides',
					items: [
						{ slug: 'schema' },
						{ slug: 'querying' },
						{ slug: 'writes' },
						{ slug: 'advanced-queries' },
						{ slug: 'connection' },
					],
				},
				{
					label: 'Migrations',
					items: [
						{ label: 'Migrations', slug: 'migrations' },
						{ label: 'Internals', slug: 'migrations-internals' },
					],
				},
				{
					label: 'Reference',
					items: [{ slug: 'configuration' }],
				},
			],
		}),
	],
});
