import { execFileSync } from 'node:child_process';
import { copyFileSync, readFileSync, writeFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

const root = fileURLToPath(new URL('.', import.meta.url));
const web = fileURLToPath(new URL('../src/agent_annotate/web/', import.meta.url));
execFileSync(root + 'node_modules/.bin/tailwindcss', ['-i', root + 'app.css', '-o', web + 'daisyui.css', '--minify'], {stdio:'inherit'});
for (const name of ['quill.js', 'quill.snow.css']) {
  const source = readFileSync(root + 'node_modules/quill/dist/' + name, 'utf8');
  writeFileSync(web + name, source.replace(/\/\/[#@] sourceMappingURL=.*$/gm, '').replace(/\/\*# sourceMappingURL=.*?\*\//g, ''));
}
copyFileSync(root + 'node_modules/quill/LICENSE', web + 'QUILL-LICENSE.txt');
copyFileSync(root + 'node_modules/quill/dist/quill.js.LICENSE.txt', web + 'quill.js.LICENSE.txt');
