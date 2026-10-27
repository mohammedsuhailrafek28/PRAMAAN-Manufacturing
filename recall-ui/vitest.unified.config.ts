// Isolated engineering checks for the stable Stitch frontend. No HTTP frontend preview.
import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';
import { fileURLToPath } from 'node:url';
const source=(p:string)=>fileURLToPath(new URL(p,import.meta.url));
export default defineConfig({
  root:source('..'),
  plugins:[react()],
  resolve:{dedupe:['react','react-dom'],alias:{
    '@':source('../stitch-nextjs/src'),
    'react':source('./node_modules/react'),
    'react-dom':source('./node_modules/react-dom'),
    'vitest':source('./node_modules/vitest/dist/index.js'),
    '@testing-library/react':source('./node_modules/@testing-library/react/dist/index.js'),
    'next/navigation':source('../stitch-nextjs/node_modules/next/navigation.js'),
    'next/link':source('../stitch-nextjs/node_modules/next/link.js'),
  }},
  test:{environment:'jsdom',globals:true,setupFiles:[source('./tests/setup.ts')],include:['compatibility/tests/**/*.test.tsx'],maxWorkers:1},
});
