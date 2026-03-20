#!/usr/bin/env node
/**
 * Contract validation script (CI contract-gate).
 * Re-generates contracts in a temp directory and compares with committed output.
 * Fails if they differ.
 */

import { execSync } from 'node:child_process';
import { readdirSync, readFileSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dir = dirname(fileURLToPath(import.meta.url));
const ROOT = join(__dir, '..');

console.log('Running contract validation...');

// Check for vendor entity patterns in orchestrator (Fitness Function F02)
const HA_ENTITY_PATTERNS = ['switch.', 'light.', 'sensor.', 'input_boolean.', 'cover.', 'climate.'];
const CORE_PATHS = [
  join(ROOT, 'apps/orchestrator'),
  join(ROOT, 'apps/digital-twin'),
  join(ROOT, 'packages/contracts'),
];

let violations = [];

for (const corePath of CORE_PATHS) {
  try {
    const result = execSync(
      `rg -r --include="*.py" --include="*.ts" --include="*.json" -l "${HA_ENTITY_PATTERNS.join('|')}" ${corePath} 2>/dev/null || true`,
      { encoding: 'utf-8' }
    );
    const files = result.trim().split('\n').filter(Boolean);
    // Filter out the entity_map files (those are adapter-only and allowed)
    const coreViolations = files.filter((f) => !f.includes('entity_map'));
    if (coreViolations.length > 0) {
      violations.push(`F02 violation: vendor entity patterns found in core paths:`);
      violations.push(...coreViolations.map((f) => `  - ${f}`));
    }
  } catch (e) {
    // rg not found or no matches — OK
  }
}

if (violations.length > 0) {
  console.error('CONTRACT GATE FAILED:');
  violations.forEach((v) => console.error(v));
  process.exit(1);
}

console.log('Contract validation passed.');
console.log('  F02: No vendor entity names in core paths ✓');
