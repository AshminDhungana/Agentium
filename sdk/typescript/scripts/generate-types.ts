/**
 * Script to fetch the OpenAPI spec from a running Agentium backend
 * and generate TypeScript interfaces.
 *
 * Usage:
 *   npx ts-node scripts/generate-types.ts [base-url]
 *
 * Default base URL: http://localhost:8000
 */

import * as fs from 'fs';
import * as path from 'path';

const BASE_URL = process.argv[2] || 'http://localhost:8000';

interface OpenAPISchema {
  type?: string;
  properties?: Record<string, OpenAPISchema>;
  items?: OpenAPISchema;
  $ref?: string;
  enum?: string[];
  allOf?: OpenAPISchema[];
  anyOf?: OpenAPISchema[];
  required?: string[];
  description?: string;
}

interface OpenAPISpec {
  components?: {
    schemas?: Record<string, OpenAPISchema>;
  };
}

function refToName(ref: string): string {
  return ref.split('/').pop() || 'unknown';
}

function schemaToTS(schema: OpenAPISchema, indent = '  '): string {
  if (schema.$ref) return refToName(schema.$ref);

  if (schema.enum) {
    return schema.enum.map((v) => `'${v}'`).join(' | ');
  }

  switch (schema.type) {
    case 'string':
      return 'string';
    case 'integer':
    case 'number':
      return 'number';
    case 'boolean':
      return 'boolean';
    case 'array':
      return schema.items ? `${schemaToTS(schema.items)}[]` : 'unknown[]';
    case 'object':
      if (!schema.properties) return 'Record<string, unknown>';
      const lines = Object.entries(schema.properties).map(([key, propSchema]) => {
        const optional = !(schema.required || []).includes(key) ? '?' : '';
        return `${indent}${key}${optional}: ${schemaToTS(propSchema, indent + '  ')};`;
      });
      return `{\n${lines.join('\n')}\n${indent.slice(2)}}`;
    default:
      if (schema.anyOf) {
        return schema.anyOf.map((s) => schemaToTS(s)).join(' | ');
      }
      if (schema.allOf) {
        return schema.allOf.map((s) => schemaToTS(s)).join(' & ');
      }
      return 'unknown';
  }
}

async function main() {
  console.log(`Fetching OpenAPI spec from ${BASE_URL}/openapi.json ...`);

  const res = await fetch(`${BASE_URL}/openapi.json`);
  if (!res.ok) {
    console.error(`Failed to fetch spec: HTTP ${res.status}`);
    process.exit(1);
  }

  const spec: OpenAPISpec = await res.json();
  const schemas = spec.components?.schemas || {};

  let output = '// Auto-generated from Agentium OpenAPI spec\n';
  output += `// Generated at: ${new Date().toISOString()}\n`;
  output += `// Source: ${BASE_URL}/openapi.json\n\n`;

  for (const [name, schema] of Object.entries(schemas)) {
    const tsType = schemaToTS(schema);
    if (tsType.startsWith('{')) {
      output += `export interface ${name} ${tsType}\n\n`;
    } else {
      output += `export type ${name} = ${tsType};\n\n`;
    }
  }

  const outPath = path.join(__dirname, '..', 'src', 'generated-types.ts');
  fs.writeFileSync(outPath, output, 'utf-8');
  console.log(`Generated ${Object.keys(schemas).length} types → ${outPath}`);
}

main().catch(console.error);
