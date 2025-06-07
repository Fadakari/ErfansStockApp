from datetime import date

pages = [
    {'loc': 'https://stockdivar.ir/', 'lastmod': '2025-05-26', 'priority': '1.0'},
    {'loc': 'https://stockdivar.ir/login', 'lastmod': '2025-05-20', 'priority': '0.8'},
    # بقیه صفحاتت رو اینجا اضافه کن
]

sitemap = '<?xml version="1.0" encoding="UTF-8"?>\n'
sitemap += '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'

for page in pages:
    sitemap += f"""  <url>
    <loc>{page['loc']}</loc>
    <lastmod>{page['lastmod']}</lastmod>
    <changefreq>weekly</changefreq>
    <priority>{page['priority']}</priority>
  </url>\n"""

sitemap += '</urlset>'

# ذخیره فایل
with open('sitemap.xml', 'w') as f:
    f.write(sitemap)

print("✅ sitemap.xml ساخته شد.")