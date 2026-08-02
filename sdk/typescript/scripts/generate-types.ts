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
import * as fs from 'fs';
import * as path from 'path';

const BASE_URL = process.argv[2] || 'http://localhost:8000';
const OUT_PATH = './src/generated-types.ts';
const LOCAL_SPEC_PATH = './openapi.json';

console.log(`Generating types...`);

try {
  // Check if local openapi.json exists
  if (fs.existsSync(LOCAL_SPEC_PATH)) {
    console.log(`Using local OpenAPI spec at ${LOCAL_SPEC_PATH}`);
    execSync(
      `npx openapi-typescript ${LOCAL_SPEC_PATH} -o ${OUT_PATH} --generate-union-enums`,
      { stdio: 'inherit' }
    );
  } else {
    console.log(`Fetching from ${BASE_URL}/openapi.json...`);
    execSync(
      `npx openapi-typescript ${BASE_URL}/openapi.json -o ${OUT_PATH} --generate-union-enums`,
      { stdio: 'inherit' }
    );
  }
  console.log(`✅ Generated ${OUT_PATH}`);
} catch (error) {
  console.error('❌ Failed to generate types');
  console.error('Ensure the backend is running at', BASE_URL);
  console.error('Or place openapi.json in the sdk/typescript directory');
  console.error('Start backend with: cd ../../backend && docker compose up -d');
  process.exit(1);
}