#!/usr/bin/env node
/**
 * Contract generation script.
 * Reads JSON Schema files from packages/contracts/schemas/ and
 * packages/assistant-contracts/schemas/ and generates:
 * - TypeScript types (packages/contracts/generated/typescript/)
 * - Python Pydantic models (packages/contracts/generated/python/)
 *
 * This is invoked by: pnpm contracts:generate
 * CI contract-gate verifies that committed generated code matches a fresh generation.
 */

import { readFileSync, writeFileSync, mkdirSync, readdirSync } from 'node:fs';
import { join, basename, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dir = dirname(fileURLToPath(import.meta.url));
const ROOT = join(__dir, '..');

const SCHEMA_DIRS = [
  { src: join(ROOT, 'packages/contracts/schemas'), prefix: '' },
  { src: join(ROOT, 'packages/assistant-contracts/schemas'), prefix: 'assistant_' },
];

const TS_OUT = join(ROOT, 'packages/contracts/generated/typescript');
const PY_OUT = join(ROOT, 'packages/contracts/generated/python');

mkdirSync(TS_OUT, { recursive: true });
mkdirSync(PY_OUT, { recursive: true });

/**
 * Generate a minimal TypeScript type file from a JSON schema.
 * Production: use json-schema-to-typescript or quicktype for full generation.
 */
function generateTypescript(schemaPath, prefix) {
  const schema = JSON.parse(readFileSync(schemaPath, 'utf-8'));
  const name = basename(schemaPath, '.schema.json');
  const typeName = name
    .split('_')
    .map((s) => s.charAt(0).toUpperCase() + s.slice(1))
    .join('');

  const lines = [
    `// AUTO-GENERATED from ${basename(schemaPath)}`,
    `// DO NOT EDIT — run pnpm contracts:generate to regenerate`,
    ``,
    `export interface ${typeName} {`,
  ];

  const props = schema.properties ?? {};
  const required = new Set(schema.required ?? []);

  for (const [key, def] of Object.entries(props)) {
    const isRequired = required.has(key);
    const tsType = jsonSchemaTypeToTs(def);
    lines.push(`  ${key}${isRequired ? '' : '?'}: ${tsType};`);
  }

  lines.push(`}`, ``);

  return lines.join('\n');
}

function jsonSchemaTypeToTs(def) {
  if (!def || typeof def !== 'object') return 'unknown';
  if (def.$ref) return 'unknown';
  if (def.oneOf) return def.oneOf.map(jsonSchemaTypeToTs).join(' | ');
  switch (def.type) {
    case 'string': return def.enum ? def.enum.map((e) => `'${e}'`).join(' | ') : 'string';
    case 'integer': case 'number': return 'number';
    case 'boolean': return 'boolean';
    case 'array': return `${jsonSchemaTypeToTs(def.items)}[]`;
    case 'object': return 'Record<string, unknown>';
    default: return 'unknown';
  }
}

/**
 * Generate a minimal Python Pydantic model from a JSON schema.
 * Production: use datamodel-code-generator for full Pydantic v2 generation.
 */
function generatePython(schemaPath, prefix) {
  const schema = JSON.parse(readFileSync(schemaPath, 'utf-8'));
  const name = basename(schemaPath, '.schema.json');
  const className = name
    .split('_')
    .map((s) => s.charAt(0).toUpperCase() + s.slice(1))
    .join('');

  const lines = [
    `# AUTO-GENERATED from ${basename(schemaPath)}`,
    `# DO NOT EDIT — run pnpm contracts:generate to regenerate`,
    `from __future__ import annotations`,
    `from typing import Any`,
    `from pydantic import BaseModel, Field`,
    ``,
    `class ${className}(BaseModel):`,
  ];

  const props = schema.properties ?? {};
  const required = new Set(schema.required ?? []);

  let hasFields = false;
  for (const [key, def] of Object.entries(props)) {
    const isRequired = required.has(key);
    const pyType = jsonSchemaTypeToPy(def);
    if (isRequired) {
      lines.push(`    ${key}: ${pyType}`);
    } else {
      lines.push(`    ${key}: ${pyType} | None = None`);
    }
    hasFields = true;
  }

  if (!hasFields) {
    lines.push(`    pass`);
  }

  lines.push(``);
  return lines.join('\n');
}

function jsonSchemaTypeToPy(def) {
  if (!def || typeof def !== 'object') return 'Any';
  if (def.$ref) return 'Any';
  if (def.oneOf) return 'Any';
  switch (def.type) {
    case 'string': return 'str';
    case 'integer': return 'int';
    case 'number': return 'float';
    case 'boolean': return 'bool';
    case 'array': return `list[${jsonSchemaTypeToPy(def.items)}]`;
    case 'object': return 'dict[str, Any]';
    default: return 'Any';
  }
}

// Generate all schemas
const tsIndexLines = [`// AUTO-GENERATED index — pnpm contracts:generate`, ``];
const pyInitLines = [`# AUTO-GENERATED __init__.py — pnpm contracts:generate`, ``];

for (const { src, prefix } of SCHEMA_DIRS) {
  const files = readdirSync(src).filter((f) => f.endsWith('.schema.json'));
  for (const file of files) {
    const schemaPath = join(src, file);
    const baseName = prefix + basename(file, '.schema.json');

    // TypeScript
    const tsContent = generateTypescript(schemaPath, prefix);
    const tsFile = join(TS_OUT, `${baseName}.ts`);
    writeFileSync(tsFile, tsContent);
    tsIndexLines.push(`export * from './${baseName}';`);
    console.log(`Generated TS: ${tsFile}`);

    // Python
    const pyContent = generatePython(schemaPath, prefix);
    const pyFile = join(PY_OUT, `${baseName}.py`);
    writeFileSync(pyFile, pyContent);
    pyInitLines.push(`from .${baseName} import *  # noqa: F401, F403`);
    console.log(`Generated Python: ${pyFile}`);
  }
}

// Write index files
writeFileSync(join(TS_OUT, 'index.ts'), tsIndexLines.join('\n') + '\n');
writeFileSync(join(PY_OUT, '__init__.py'), pyInitLines.join('\n') + '\n');

console.log('\nContract generation complete.');
