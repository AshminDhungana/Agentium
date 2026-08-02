/**
 * Script to fetch the OpenAPI spec from a running Agentium backend
 * and generate TypeScript interfaces using openapi-typescript CLI.
 *
 * Usage:
 *   npm run generate-types [base-url]
 *
 * Default base URL: http://localhost:8000
 */

import { execSync } from 'child_process';

const BASE_URL = process.argv[2] || 'http://localhost:8000';
const OUT_PATH = './src/generated-types.ts';

console.log(`Generating types from ${BASE_URL}/openapi.json...`);

try {
  execSync(
    `npx openapi-typescript ${BASE_URL}/openapi.json -o ${OUT_PATH} --generate-union-enums`,
    { stdio: 'inherit' }
  );
  console.log(`✅ Generated ${OUT_PATH}`);
} catch (error) {
  console.error('❌ Failed to generate types');
  console.error('Ensure the backend is running at', BASE_URL);
  console.error('Start it with: cd ../../backend && docker compose up -d');
  process.exit(1);
}