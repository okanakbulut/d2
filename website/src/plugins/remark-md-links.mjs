import { visit } from 'unist-util-visit';

const BASE = '/d2';

/**
 * Rewrite relative links between sibling docs pages (`querying.md`,
 * `./index.md#anchor`, …) to their site routes under the deploy base path.
 * The sources keep plain `.md` links so they stay navigable on GitHub.
 */
export default function remarkMdLinks() {
	return (tree) => {
		visit(tree, 'link', (node) => {
			if (/^[a-z][a-z+.-]*:/i.test(node.url)) return; // absolute URL
			const match = /^(?:\.\/)?([\w-]+)\.md(#[\w-]+)?$/.exec(node.url);
			if (!match) return;
			const slug = match[1] === 'index' ? '' : `${match[1]}/`;
			node.url = `${BASE}/${slug}${match[2] ?? ''}`;
		});
	};
}
