#!/usr/bin/env node
/**
 * ASCII-Türkçe Kelime Lint
 *
 * UI kodlarında ASCII-Türkçe kullanımını tespit eder ve uyarı verir.
 * Ör: "Musteri" yerine "Müşteri" kullanılmalı.
 *
 * Kullanım:
 *   node scripts/lint-turkish.mjs                  # uyarı listesi, exit 0
 *   node scripts/lint-turkish.mjs --strict         # tespit varsa exit 1 (CI için)
 *   node scripts/lint-turkish.mjs --staged         # sadece git staged dosyaları
 */

import fs from 'node:fs';
import path from 'node:path';
import { execSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const ROOT = path.resolve(__dirname, '..');

// ASCII-Türkçe — proper karakterlerle yazılmalı
const ASCII_TURKISH_WORDS = [
  'Musteri', 'Musteriler', 'Musterisi', 'Musteriye', 'musteri', 'musteriler',
  'Sirket', 'Sirketi', 'sirket',
  'Firsat', 'Firsatlar', 'Firsati', 'firsat',
  'Parca', 'Parcalar', 'Parcasi', 'parca',
  'Duzenle', 'Duzenleme', 'duzenle',
  'Iptal', 'iptal',
  'Ayristir', 'Ayristirildi', 'Ayristirma', 'ayristir',
  'Gorusme', 'Gorusmeler', 'gorusme',
  'Ozet', 'ozet', 'Oneri', 'Oneriler', 'oneri',
  'Ozel', 'ozel',
  'Asama', 'asama',
  'Basarili', 'Basarisiz', 'basarili', 'basarisiz',
  'Ilerleme', 'ilerleme',
  'Bolge', 'Bolgeler', 'bolge',
  'Yonetim', 'Yonetimi', 'yonetim',
  'Uretim', 'uretim',
  'Urun', 'Urunler', 'urun', 'urunler',
  'Sablon', 'Sablonu', 'Sablonlari', 'sablon',
  'Siralama', 'siralama',
  'Goruntule', 'Goruntuleyen', 'goruntule',
  'Olustu', 'Olusturuldu', 'Olusturulamadi', 'Olustur',
  'olustu', 'olusturuldu', 'olustur',
  'Sec', 'Secim', 'Secenek', 'Secilen', 'sec', 'secim',
  'Satis', 'satis',
  'Kullanici', 'Kullanicilar', 'kullanici',
  'Kocluk', 'kocluk',
  'Hizli', 'hizli',
  'Canli', 'canli',
  'Analitigi', 'analitigi',
  'Izin', 'Izinler', 'izin',
  'Dusuk', 'dusuk',
  'Yuksek', 'yuksek',
  'Kurallari', 'kurali', 'Kurali',
  'Gonder', 'Gonderen', 'Gonderildi', 'gonder',
  'Etkilesim', 'etkilesim',
  'Erisim', 'erisim',
  'Tanima', 'tanima',
];

// Eksclude dosyalar (i18n'de tüm diller olabilir)
const EXCLUDE_FILES = new Set([
  'src/lib/i18n.ts',
  'scripts/fix-turkish-chars.mjs',
  'scripts/lint-turkish.mjs',
]);

const INCLUDE_EXT = ['.ts', '.tsx'];

function getTargetFiles(staged) {
  if (staged) {
    try {
      const out = execSync('git diff --cached --name-only --diff-filter=ACM', {
        cwd: ROOT,
        encoding: 'utf8',
      });
      return out
        .split('\n')
        .filter(f => f && INCLUDE_EXT.some(ext => f.endsWith(ext)))
        .filter(f => !EXCLUDE_FILES.has(f));
    } catch {
      return [];
    }
  }

  // All frontend files
  const files = [];
  const walk = (dir) => {
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      const full = path.join(dir, entry.name);
      const rel = path.relative(ROOT, full);
      if (entry.isDirectory()) {
        if (['node_modules', 'dist', '.git', '.turbo', 'build'].includes(entry.name)) continue;
        walk(full);
      } else if (INCLUDE_EXT.includes(path.extname(entry.name))) {
        if (!EXCLUDE_FILES.has(rel)) files.push(rel);
      }
    }
  };
  walk(path.join(ROOT, 'frontend/src'));
  return files;
}

function checkFile(filePath) {
  const content = fs.readFileSync(path.join(ROOT, filePath), 'utf8');
  const lines = content.split('\n');
  const findings = [];
  const pattern = new RegExp(`(?<![A-Za-zÇĞİÖŞÜçğıöşü_0-9])(${ASCII_TURKISH_WORDS.join('|')})(?![A-Za-zÇĞİÖŞÜçğıöşü_0-9])`, 'g');

  lines.forEach((line, idx) => {
    // Skip comments
    const trimmed = line.trim();
    if (trimmed.startsWith('//') || trimmed.startsWith('*') || trimmed.startsWith('/*')) return;
    // Skip JSX comments {/* ... */}
    if (trimmed.startsWith('{/*')) return;
    // Skip import paths
    if (trimmed.startsWith('import ') || (trimmed.startsWith('export ') && trimmed.includes(' from '))) return;
    // Skip localStorage-style identifier keys (e.g. 'sidebar-yedek-parca-collapsed')
    if (/['"][a-z][a-z0-9_-]*-[a-z0-9_-]+['"]/i.test(line) && !/['"][A-ZÇĞİÖŞÜ]/i.test(line.replace(/['"][a-z][a-z0-9_-]*-[a-z0-9_-]+['"]/g, ''))) {
      // Line contains kebab-case id string — likely storage key or API key
      const afterStrip = line.replace(/['"][a-z][a-z0-9_-]*-[a-z0-9_-]+['"]/g, '');
      if (!pattern.test(afterStrip)) return;
      pattern.lastIndex = 0;
    }
    // Skip dict KEY pattern: 'iptal': anything  (backend enum mapping)
    // e.g. "iptal: 'İptal'" or "'iptal': 'danger'" or "{ value: 'iptal', ... }"
    if (/(^|[{,\s])['"]?(iptal|musteri|firsat|parca|sirket|asama|bolge|kullanici)['"]?\s*:/.test(line)) {
      // Treat dict KEY as backend enum → skip
      return;
    }
    if (/value:\s*['"](iptal|musteri|firsat|parca)['"]/.test(line)) return;
    // Skip "iptal edildi" (valid Turkish phrase, no ASCII-Turkish)
    if (/\biptal edildi\b/.test(line)) return;

    const matches = [...line.matchAll(pattern)];
    for (const m of matches) {
      findings.push({
        line: idx + 1,
        col: m.index + 1,
        word: m[1],
        context: line.trim().slice(0, 120),
      });
    }
  });
  return findings;
}

// Main
const args = process.argv.slice(2);
const strict = args.includes('--strict');
const staged = args.includes('--staged');

const files = getTargetFiles(staged);
let totalFindings = 0;
const fileFindings = [];

for (const file of files) {
  const findings = checkFile(file);
  if (findings.length > 0) {
    fileFindings.push({ file, findings });
    totalFindings += findings.length;
  }
}

if (totalFindings === 0) {
  console.log('✅ Türkçe karakter lint: hata yok.');
  process.exit(0);
}

console.log(`⚠️  ${totalFindings} ASCII-Türkçe kullanımı bulundu (${fileFindings.length} dosyada):\n`);

for (const { file, findings } of fileFindings.slice(0, 30)) {
  console.log(`  ${file}:`);
  for (const f of findings.slice(0, 5)) {
    console.log(`    ${f.line}:${f.col}  "${f.word}"  ${f.context.slice(0, 80)}`);
  }
  if (findings.length > 5) {
    console.log(`    ... ${findings.length - 5} more`);
  }
}
if (fileFindings.length > 30) {
  console.log(`\n  ... and ${fileFindings.length - 30} more files`);
}

console.log('\nDoğru Türkçe karakter kullanın: ş, ç, ğ, ı, İ, ö, ü');
console.log('Örn: "Musteri" → "Müşteri", "Firsat" → "Fırsat", "Duzenle" → "Düzenle"');

if (strict) {
  process.exit(1);
}
process.exit(0);
