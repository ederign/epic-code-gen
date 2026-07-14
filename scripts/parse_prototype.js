#!/usr/bin/env node
/**
 * Parse a UX prototype HTML file, extract scenarios via Playwright,
 * and produce a structured summary with screenshots.
 *
 * Usage: node scripts/parse_prototype.js <html-file> <output-dir>
 */

const { chromium } = require('playwright');
const http = require('http');
const fs = require('fs');
const path = require('path');

const SCENARIO_PICKER_GUARD = '<!-- Scenario picker -->';
const SCENARIO_CONTENT_GUARD = '<!-- Scenario content container -->';

function slugify(text) {
  return text
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-|-$/g, '')
    .substring(0, 50);
}

function startServer(dir, port) {
  return new Promise((resolve, reject) => {
    const server = http.createServer((req, res) => {
      const filePath = path.join(dir, decodeURIComponent(req.url));
      if (!fs.existsSync(filePath)) {
        res.writeHead(404);
        res.end('Not found');
        return;
      }
      const ext = path.extname(filePath).toLowerCase();
      const mimeTypes = {
        '.html': 'text/html',
        '.css': 'text/css',
        '.js': 'application/javascript',
        '.png': 'image/png',
        '.jpg': 'image/jpeg',
        '.svg': 'image/svg+xml',
      };
      res.writeHead(200, { 'Content-Type': mimeTypes[ext] || 'application/octet-stream' });
      fs.createReadStream(filePath).pipe(res);
    });
    server.on('error', reject);
    server.listen(port, '127.0.0.1', () => resolve(server));
  });
}

function isVisible(el) {
  if (!el) return false;
  const style = window.getComputedStyle(el);
  if (style.display === 'none' || style.visibility === 'hidden') return false;
  if (el.hasAttribute('hidden')) return false;
  const parent = el.parentElement;
  if (parent && parent !== document.body) return isVisible(parent);
  return true;
}

function ownText(el) {
  let text = '';
  for (const node of el.childNodes) {
    if (node.nodeType === Node.TEXT_NODE) text += node.textContent;
  }
  return text.trim();
}

async function extractAlerts(page, container) {
  return page.$$eval(
    `${container} .pf-v6-c-alert, ${container} .pf-v5-c-alert`,
    (els, _isVisible) => {
      const fn = new Function('el', `const isVisible = ${_isVisible}; return isVisible(el);`);
      const seen = new Set();
      return els
        .filter((el) => fn(el))
        .map((el) => {
          const classList = [...el.classList];
          let variant = 'info';
          if (classList.some((c) => c.includes('warning'))) variant = 'warning';
          if (classList.some((c) => c.includes('danger'))) variant = 'danger';
          if (classList.some((c) => c.includes('success'))) variant = 'success';
          const titleEl = el.querySelector('[class*="alert__title"]');
          const title = titleEl ? titleEl.textContent.replace(/^.*?:\s*/, '').trim() : '';
          const descEl = el.querySelector('[class*="alert__description"]');
          const description = descEl ? descEl.textContent.trim() : '';
          const actions = [...el.querySelectorAll('[class*="alert__action-group"] button')].map(
            (a) => a.textContent.trim()
          );
          if (!title) return null;
          const key = title;
          if (seen.has(key)) return null;
          seen.add(key);
          return { variant, title, description, actions };
        })
        .filter(Boolean);
    },
    isVisible.toString()
  );
}

async function extractDisabledStates(page, container) {
  return page.$$eval(
    `${container} input:disabled, ${container} button:disabled, ${container} select:disabled`,
    (els, _isVisible) => {
      const fn = new Function('el', `const isVisible = ${_isVisible}; return isVisible(el);`);
      const seen = new Set();
      return els
        .filter((el) => fn(el))
        .map((el) => {
          const radioDiv = el.closest('[class*="radio"]');
          let label = '';
          if (radioDiv) {
            const labelEl = radioDiv.querySelector('label');
            if (labelEl) {
              let text = '';
              for (const node of labelEl.childNodes) {
                if (node.nodeType === Node.TEXT_NODE) text += node.textContent;
              }
              label = text.trim();
            }
          }
          if (!label) label = el.getAttribute('aria-label') || '';
          if (!label) return null;
          if (seen.has(label)) return null;
          seen.add(label);
          return { element: el.tagName.toLowerCase(), label };
        })
        .filter(Boolean);
    },
    isVisible.toString()
  );
}

async function extractComponentInventory(page, container) {
  return page.$$eval(
    `${container} [class*="pf-v6-c-"], ${container} [class*="pf-v5-c-"]`,
    (els, _isVisible) => {
      const fn = new Function('el', `const isVisible = ${_isVisible}; return isVisible(el);`);
      const components = new Map();
      els
        .filter((el) => fn(el))
        .forEach((el) => {
          [...el.classList].forEach((cls) => {
            const match = cls.match(/pf-v[56]-c-([a-z-]+)/);
            if (!match) return;
            const name = match[1];
            if (!components.has(name)) components.set(name, new Set());
            [...el.classList].forEach((c) => {
              const variantMatch = c.match(/pf-m-([a-z-]+)/);
              if (variantMatch) components.get(name).add(variantMatch[1]);
            });
          });
        });
      const result = {};
      components.forEach((variants, name) => {
        result[name] = [...variants];
      });
      return result;
    },
    isVisible.toString()
  );
}

async function extractFormLabels(page, container) {
  return page.$$eval(
    `${container} [class*="form__label-text"]`,
    (els, _isVisible) => {
      const fn = new Function('el', `const isVisible = ${_isVisible}; return isVisible(el);`);
      return [
        ...new Set(
          els
            .filter((el) => fn(el))
            .map((el) => {
              let text = '';
              for (const node of el.childNodes) {
                if (node.nodeType === Node.TEXT_NODE) text += node.textContent;
              }
              return text.trim();
            })
            .filter((t) => t && t.length < 100)
        ),
      ];
    },
    isVisible.toString()
  );
}

async function extractHelperText(page, container) {
  return page.$$eval(
    `${container} [class*="helper-text__item-text"]`,
    (els, _isVisible) => {
      const fn = new Function('el', `const isVisible = ${_isVisible}; return isVisible(el);`);
      return [
        ...new Set(
          els
            .filter((el) => fn(el))
            .map((el) => el.textContent.trim())
            .filter((t) => t && t.length < 300)
        ),
      ];
    },
    isVisible.toString()
  );
}

async function extractPopoverContent(page, container) {
  return page.$$eval(
    `${container} [class*="popover__body"]`,
    (els) =>
      els
        .map((el) => el.textContent.trim())
        .filter((t) => t && t.length < 300)
  );
}

async function extractCheckboxes(page, container) {
  return page.$$eval(
    `${container} input[type="checkbox"][class*="check__input"]`,
    (els, _isVisible) => {
      const fn = new Function('el', `const isVisible = ${_isVisible}; return isVisible(el);`);
      return els
        .filter((el) => fn(el))
        .map((el) => {
          const labelEl = el.nextElementSibling;
          let label = '';
          if (labelEl) {
            for (const node of labelEl.childNodes) {
              if (node.nodeType === Node.TEXT_NODE) label += node.textContent;
            }
          }
          label = label.trim();
          if (!label) return null;
          return { label, checked: el.checked };
        })
        .filter(Boolean);
    },
    isVisible.toString()
  );
}

async function extractRadioButtons(page, container) {
  return page.$$eval(
    `${container} input[type="radio"][class*="radio__input"]`,
    (els, _isVisible) => {
      const fn = new Function('el', `const isVisible = ${_isVisible}; return isVisible(el);`);
      return els
        .filter((el) => fn(el))
        .map((el) => {
          const labelEl = el.nextElementSibling;
          let label = '';
          if (labelEl) {
            // Try own text first
            for (const node of labelEl.childNodes) {
              if (node.nodeType === Node.TEXT_NODE) label += node.textContent;
            }
            label = label.trim();
            // If label wraps text in a child span (e.g. form__label-text), use that
            if (!label) {
              const innerSpan = labelEl.querySelector('[class*="label-text"]');
              if (innerSpan) label = innerSpan.textContent.trim();
            }
            // Last resort: full textContent but capped
            if (!label) {
              label = labelEl.textContent.trim().substring(0, 80);
            }
          }
          if (!label) return null;
          return { label, checked: el.checked, disabled: el.disabled };
        })
        .filter(Boolean);
    },
    isVisible.toString()
  );
}

async function extractBadges(page, container) {
  return page.$$eval(
    `${container} [class*="c-badge"]`,
    (els, _isVisible) => {
      const fn = new Function('el', `const isVisible = ${_isVisible}; return isVisible(el);`);
      return [
        ...new Set(
          els
            .filter((el) => fn(el))
            .map((el) => el.textContent.trim())
            .filter((t) => t && t.length < 100)
        ),
      ];
    },
    isVisible.toString()
  );
}

function formatComponentInventory(inventory) {
  const lines = [];
  const sorted = Object.entries(inventory).sort(([a], [b]) => a.localeCompare(b));
  for (const [name, variants] of sorted) {
    const pfName = name
      .split('-')
      .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
      .join('');
    if (variants.length > 0) {
      lines.push(`- ${pfName} (variants: ${variants.join(', ')})`);
    } else {
      lines.push(`- ${pfName}`);
    }
  }
  return lines.join('\n');
}

function writeScenarioMd(outputDir, index, slug, scenario) {
  const lines = [];
  lines.push(`# Scenario ${index}: ${scenario.name}`);
  lines.push('');
  if (scenario.description) {
    lines.push(`**Description:** ${scenario.description}`);
    lines.push('');
  }

  if (scenario.alerts.length > 0) {
    lines.push('## Alerts');
    for (const alert of scenario.alerts) {
      lines.push(`- **${alert.variant}**: ${alert.title}`);
      if (alert.description) lines.push(`  ${alert.description}`);
      if (alert.actions.length > 0) lines.push(`  Actions: ${alert.actions.join(', ')}`);
    }
    lines.push('');
  }

  if (scenario.disabledStates.length > 0) {
    lines.push('## Disabled Elements');
    for (const d of scenario.disabledStates) {
      lines.push(`- ${d.label} (${d.element})`);
    }
    lines.push('');
  }

  if (scenario.radioButtons.length > 0) {
    lines.push('## Radio Buttons');
    for (const r of scenario.radioButtons) {
      const state = r.disabled ? 'disabled' : r.checked ? 'selected' : 'unselected';
      lines.push(`- ${r.label}: ${state}`);
    }
    lines.push('');
  }

  if (scenario.checkboxes.length > 0) {
    lines.push('## Checkboxes');
    for (const c of scenario.checkboxes) {
      lines.push(`- ${c.label}: ${c.checked ? 'checked' : 'unchecked'}`);
    }
    lines.push('');
  }

  if (scenario.formLabels.length > 0) {
    lines.push('## Form Fields');
    for (const label of scenario.formLabels) {
      lines.push(`- ${label}`);
    }
    lines.push('');
  }

  if (scenario.helperText.length > 0) {
    lines.push('## Helper Text');
    for (const text of scenario.helperText) {
      lines.push(`- ${text}`);
    }
    lines.push('');
  }

  if (scenario.popoverContent.length > 0) {
    lines.push('## Popover Content');
    for (const text of scenario.popoverContent) {
      lines.push(`- ${text}`);
    }
    lines.push('');
  }

  if (scenario.badges.length > 0) {
    lines.push('## Badges');
    for (const badge of scenario.badges) {
      lines.push(`- ${badge}`);
    }
    lines.push('');
  }

  lines.push('## Component Inventory');
  lines.push(formatComponentInventory(scenario.componentInventory));
  lines.push('');

  lines.push(`## Screenshot`);
  lines.push(`![Scenario ${index}](scenario-${index}-${slug}.png)`);
  lines.push('');

  const filePath = path.join(outputDir, `scenario-${index}-${slug}.md`);
  fs.writeFileSync(filePath, lines.join('\n'));
  return filePath;
}

function writeSummary(outputDir, sourceFile, scenarios, globalInventory) {
  const lines = [];
  lines.push('# Prototype Analysis');
  lines.push('');
  lines.push(`**Source:** ${path.basename(sourceFile)}`);
  lines.push(`**Scenarios:** ${scenarios.length}`);
  lines.push('');

  lines.push('## Component Inventory');
  lines.push('');
  lines.push(formatComponentInventory(globalInventory));
  lines.push('');

  lines.push('## Scenarios');
  lines.push('');

  for (const s of scenarios) {
    lines.push(`### Scenario ${s.index}: ${s.name}`);
    if (s.description) lines.push(`**Description:** ${s.description}`);
    lines.push('');

    if (s.alerts.length > 0) {
      lines.push('**Alerts:**');
      for (const alert of s.alerts) {
        lines.push(`- ${alert.variant}: ${alert.title}`);
        if (alert.description) lines.push(`  ${alert.description}`);
        if (alert.actions.length > 0) lines.push(`  Actions: ${alert.actions.join(', ')}`);
      }
      lines.push('');
    }

    if (s.disabledStates.length > 0) {
      lines.push('**Disabled elements:**');
      for (const d of s.disabledStates) {
        lines.push(`- ${d.label}`);
      }
      lines.push('');
    }

    if (s.radioButtons.filter((r) => r.checked || r.disabled).length > 0) {
      lines.push('**State:**');
      for (const r of s.radioButtons.filter((rb) => rb.checked || rb.disabled)) {
        const state = r.disabled ? 'disabled' : 'selected';
        lines.push(`- ${r.label}: ${state}`);
      }
      lines.push('');
    }

    if (s.checkboxes.length > 0) {
      const checked = s.checkboxes.filter((c) => c.checked);
      const unchecked = s.checkboxes.filter((c) => !c.checked);
      if (checked.length > 0) {
        lines.push(`**Selected:** ${checked.map((c) => c.label).join(', ')}`);
      }
      if (unchecked.length > 0) {
        lines.push(`**Unselected:** ${unchecked.map((c) => c.label).join(', ')}`);
      }
      lines.push('');
    }

    if (s.popoverContent.length > 0) {
      lines.push('**Popover messages:**');
      for (const p of s.popoverContent) {
        lines.push(`- ${p}`);
      }
      lines.push('');
    }

    if (s.helperText.length > 0) {
      lines.push('**Helper text:**');
      for (const h of s.helperText) {
        lines.push(`- ${h}`);
      }
      lines.push('');
    }

    lines.push(`**Screenshot:** scenario-${s.index}-${s.slug}.png`);
    lines.push('');
  }

  const filePath = path.join(outputDir, 'prototype-summary.md');
  fs.writeFileSync(filePath, lines.join('\n'));
  return filePath;
}

async function main() {
  const args = process.argv.slice(2);
  if (args.length < 2) {
    console.error('Usage: node scripts/parse_prototype.js <html-file> <output-dir>');
    process.exit(1);
  }

  const htmlFile = path.resolve(args[0]);
  const outputDir = path.resolve(args[1]);

  if (!fs.existsSync(htmlFile)) {
    console.error(`Error: HTML file not found: ${htmlFile}`);
    process.exit(1);
  }

  const htmlContent = fs.readFileSync(htmlFile, 'utf-8');
  const hasScenarioPicker = htmlContent.includes(SCENARIO_PICKER_GUARD);

  if (!hasScenarioPicker) {
    console.warn(`Warning: ${SCENARIO_PICKER_GUARD} not found in ${htmlFile}`);
    console.warn('Falling back to single-scenario extraction.');
  }

  fs.mkdirSync(outputDir, { recursive: true });

  // Copy source HTML for audit trail
  fs.copyFileSync(htmlFile, path.join(outputDir, 'source.html'));

  const htmlDir = path.dirname(htmlFile);
  const htmlFileName = path.basename(htmlFile);

  // Find an available port
  const port = 18700 + Math.floor(Math.random() * 300);
  const server = await startServer(htmlDir, port);
  const url = `http://127.0.0.1:${port}/${encodeURIComponent(htmlFileName)}`;

  let browser;
  try {
    browser = await chromium.launch({ headless: true });
    const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
    await page.goto(url, { waitUntil: 'domcontentloaded' });
    // Wait for JS to execute
    await page.waitForTimeout(1000);

    const scenarios = [];
    const globalInventory = {};

    if (hasScenarioPicker) {
      // Find scenario items
      const scenarioItems = await page.$$eval('[data-scenario]', (items) =>
        items.map((item) => ({
          index: item.getAttribute('data-scenario'),
          name:
            item.querySelector('[class*="menu__item-text"]')?.textContent?.trim() ||
            item.textContent.trim().split('\n')[0].trim(),
          description:
            item.querySelector('[class*="menu__item-description"]')?.textContent?.trim() || '',
        }))
      );

      if (scenarioItems.length === 0) {
        console.warn('Warning: Scenario picker found but no [data-scenario] items detected.');
      }

      console.log(`Found ${scenarioItems.length} scenarios`);

      for (const item of scenarioItems) {
        console.log(`  Parsing scenario ${item.index}: ${item.name}`);

        // Find and click the scenario toggle to open the dropdown
        const toggleSelector = '[id*="scenario-toggle"], [id*="scenario"] [class*="menu-toggle"]';
        const toggle = await page.$(toggleSelector);
        if (toggle) {
          await toggle.click();
          await page.waitForTimeout(200);
        }

        // Click the scenario item
        await page.click(`[data-scenario="${item.index}"]`);
        await page.waitForTimeout(500);

        // Find the scenario content container via the HTML comment guard
        const containerId = await page.evaluate((guard) => {
          const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_COMMENT);
          while (walker.nextNode()) {
            if (walker.currentNode.textContent.trim() === guard.replace('<!--', '').replace('-->', '').trim()) {
              let sibling = walker.currentNode.nextSibling;
              while (sibling && sibling.nodeType !== Node.ELEMENT_NODE) sibling = sibling.nextSibling;
              if (sibling && sibling.id) return '#' + sibling.id;
              if (sibling) {
                sibling.id = '__proto_content__';
                return '#__proto_content__';
              }
            }
          }
          return null;
        }, SCENARIO_CONTENT_GUARD);
        const container = containerId || '[id*="scenario-content"]';

        // Extract data from rendered DOM
        const alerts = await extractAlerts(page, container);
        const disabledStates = await extractDisabledStates(page, container);
        const componentInventory = await extractComponentInventory(page, container);
        const formLabels = await extractFormLabels(page, container);
        const helperText = await extractHelperText(page, container);
        const popoverContent = await extractPopoverContent(page, container);
        const checkboxes = await extractCheckboxes(page, container);
        const radioButtons = await extractRadioButtons(page, container);
        const badges = await extractBadges(page, container);

        // Merge into global inventory
        for (const [comp, variants] of Object.entries(componentInventory)) {
          if (!globalInventory[comp]) globalInventory[comp] = new Set();
          variants.forEach((v) => globalInventory[comp].add(v));
        }

        const slug = slugify(item.name);

        // Screenshot only the scenario content container (not the picker)
        const contentEl = await page.$(container);
        if (contentEl) {
          await contentEl.scrollIntoViewIfNeeded();
          await page.waitForTimeout(200);
          await contentEl.screenshot({
            path: path.join(outputDir, `scenario-${item.index}-${slug}.png`),
          });
        } else {
          await page.screenshot({
            path: path.join(outputDir, `scenario-${item.index}-${slug}.png`),
            fullPage: true,
          });
        }

        const scenarioData = {
          index: item.index,
          name: item.name,
          description: item.description,
          slug,
          alerts,
          disabledStates,
          componentInventory,
          formLabels,
          helperText,
          popoverContent,
          checkboxes,
          radioButtons,
          badges,
        };

        scenarios.push(scenarioData);
        writeScenarioMd(outputDir, item.index, slug, scenarioData);
      }
    } else {
      // Single-scenario fallback — extract whatever is visible
      console.log('Single-scenario fallback: extracting visible page content');
      const container = 'body';
      const alerts = await extractAlerts(page, container);
      const disabledStates = await extractDisabledStates(page, container);
      const componentInventory = await extractComponentInventory(page, container);
      const formLabels = await extractFormLabels(page, container);
      const helperText = await extractHelperText(page, container);
      const popoverContent = await extractPopoverContent(page, container);
      const checkboxes = await extractCheckboxes(page, container);
      const radioButtons = await extractRadioButtons(page, container);
      const badges = await extractBadges(page, container);

      Object.assign(globalInventory, componentInventory);

      const scenarioData = {
        index: '0',
        name: 'Default',
        description: 'Single page (no scenario picker)',
        slug: 'default',
        alerts,
        disabledStates,
        componentInventory,
        formLabels,
        helperText,
        popoverContent,
        checkboxes,
        radioButtons,
        badges,
      };

      scenarios.push(scenarioData);
      writeScenarioMd(outputDir, '0', 'default', scenarioData);
      await page.screenshot({
        path: path.join(outputDir, 'scenario-0-default.png'),
        fullPage: true,
      });
    }

    // Convert global inventory sets to arrays for JSON serialization
    const globalInvForSummary = {};
    for (const [k, v] of Object.entries(globalInventory)) {
      globalInvForSummary[k] = v instanceof Set ? [...v] : v;
    }

    writeSummary(outputDir, htmlFile, scenarios, globalInvForSummary);

    console.log(`\nPrototype analysis written to ${outputDir}/`);
    console.log(`  - prototype-summary.md`);
    console.log(`  - ${scenarios.length} scenario files + screenshots`);
    console.log(`  - source.html (copy)`);
  } finally {
    if (browser) await browser.close();
    server.close();
  }
}

main().catch((err) => {
  console.error('Fatal error:', err.message);
  process.exit(1);
});
