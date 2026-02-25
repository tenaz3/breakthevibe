#!/usr/bin/env bash
set -euo pipefail

echo "Seeding database with sample data..."

python -c "
import asyncio
import httpx

async def seed():
    async with httpx.AsyncClient(base_url='http://localhost:8000') as client:
        # Create sample project
        resp = await client.post('/api/projects', json={
            'name': 'Example Store',
            'url': 'https://example.com',
            'rules_yaml': '''
crawl:
  max_depth: 3
  skip_urls: [\"/admin/*\"]
tests:
  skip_visual: [\"/404\"]
'''
        })
        project = resp.json()
        print(f\"Created project: {project['id']} - {project['name']}\")

asyncio.run(seed())
"

echo "Seeding complete."
