#!/usr/bin/env node
/**
 * ASCII→Türkçe dönüştürücü
 *
 * Sadece string literal'ları ve JSX text node'larını hedefler.
 * Identifier'lara, prop key'lerine, URL'lere, import path'lerine dokunmaz.
 *
 * Kullanım:
 *   node scripts/fix-turkish-chars.mjs --dry-run  # Değişikliği göster, uygulama
 *   node scripts/fix-turkish-chars.mjs            # Uygula
 *   node scripts/fix-turkish-chars.mjs --root frontend/src
 */

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// ── Kelime Haritası (TAM EŞLEME — case-sensitive) ──
// Sadece tek kelime ya da çok sık geçen ifadeler.
// Bağlama duyarsız olmalı (yani kelime her yerde aynı anlama gelmeli).
const WORD_MAP = {
  // Müşteri & Şirket
  Musteri: 'Müşteri',
  Musteriler: 'Müşteriler',
  Musterisi: 'Müşterisi',
  Musteriye: 'Müşteriye',
  Musterinin: 'Müşterinin',
  Musterisinin: 'Müşterisinin',
  Musterilerim: 'Müşterilerim',
  musteri: 'müşteri',
  musteriler: 'müşteriler',
  musterisi: 'müşterisi',
  Sirket: 'Şirket',
  Sirketi: 'Şirketi',
  sirket: 'şirket',
  sirketi: 'şirketi',

  // Fırsat & Teklif
  Firsat: 'Fırsat',
  Firsatlar: 'Fırsatlar',
  Firsati: 'Fırsatı',
  firsat: 'fırsat',
  firsatlar: 'fırsatlar',
  // Teklif already correct (no Turkish diacritics)

  // Parça
  Parca: 'Parça',
  Parcalar: 'Parçalar',
  Parcasi: 'Parçası',
  parca: 'parça',
  parcalar: 'parçalar',
  parcasi: 'parçası',

  // Aksiyon kelimeleri
  Duzenle: 'Düzenle',
  Duzenleme: 'Düzenleme',
  Duzenlendi: 'Düzenlendi',
  duzenle: 'düzenle',
  duzenleme: 'düzenleme',
  Iptal: 'İptal',
  iptal: 'iptal',
  Onay: 'Onay', // OK
  Onaylandi: 'Onaylandı',
  onaylandi: 'onaylandı',
  Reddet: 'Reddet', // OK
  Reddedildi: 'Reddedildi', // OK
  Gonder: 'Gönder',
  Gonderildi: 'Gönderildi',
  Gonderen: 'Gönderen',
  gonder: 'gönder',
  gonderildi: 'gönderildi',
  gonderen: 'gönderen',

  // Ayrıştırma
  Ayristir: 'Ayrıştır',
  Ayristirildi: 'Ayrıştırıldı',
  Ayristirma: 'Ayrıştırma',
  ayristir: 'ayrıştır',
  ayristirildi: 'ayrıştırıldı',
  ayristirma: 'ayrıştırma',
  Ayristirma: 'Ayrıştırma',

  // Görüşme / İletişim
  Gorusme: 'Görüşme',
  Gorusmeler: 'Görüşmeler',
  Gorusmesi: 'Görüşmesi',
  gorusme: 'görüşme',
  gorusmeler: 'görüşmeler',

  // Özet / Önemli
  Ozet: 'Özet',
  Ozeti: 'Özeti',
  ozet: 'özet',
  Oneri: 'Öneri',
  Oneriler: 'Öneriler',
  oneri: 'öneri',
  oneriler: 'öneriler',
  Onerilen: 'Önerilen',
  onerilen: 'önerilen',
  Ozel: 'Özel',
  ozel: 'özel',
  Onemli: 'Önemli',
  onemli: 'önemli',

  // Durum
  Asama: 'Aşama',
  Asamasi: 'Aşaması',
  asama: 'aşama',
  asamasi: 'aşaması',
  Basarili: 'Başarılı',
  Basarisiz: 'Başarısız',
  basarili: 'başarılı',
  basarisiz: 'başarısız',
  Ilerleme: 'İlerleme',
  ilerleme: 'ilerleme',
  Ilerledi: 'İlerledi',
  Islem: 'İşlem',
  Islemler: 'İşlemler',
  islem: 'işlem',
  islemler: 'işlemler',

  // Bölge / Yönetim
  Bolge: 'Bölge',
  Bolgeler: 'Bölgeler',
  bolge: 'bölge',
  bolgeler: 'bölgeler',
  Yonetim: 'Yönetim',
  Yonetimi: 'Yönetimi',
  Yoneticiye: 'Yöneticiye',
  yonetim: 'yönetim',
  yonetimi: 'yönetimi',

  // Üretim / Ürün
  Uretim: 'Üretim',
  uretim: 'üretim',
  Urun: 'Ürün',
  Urunler: 'Ürünler',
  urun: 'ürün',
  urunler: 'ürünler',

  // Iş / İş Akışı
  Is: 'İş',
  Isleyis: 'İşleyiş',
  // "Is" ile tek başına değiştirme — çok kısa, başka İngilizce kelimede var olabilir
  // Bu yüzden sadece bağlamlı kullanımları ekleyelim:
  'Is Kurallari': 'İş Kuralları',
  'is kurallari': 'iş kuralları',
  'Is Akisi': 'İş Akışı',
  Kurallari: 'Kuralları',
  kurallari: 'kuralları',
  kurali: 'kuralı',
  Kurali: 'Kuralı',

  // Şablon / Sistem / Setting
  Sablon: 'Şablon',
  Sablonu: 'Şablonu',
  Sablonlari: 'Şablonları',
  sablon: 'şablon',
  sablonu: 'şablonu',
  sablonlari: 'şablonları',

  // Sözleşme / Ödeme
  Kontrat: 'Kontrat', // OK
  Odeme: 'Ödeme',
  Odendi: 'Ödendi',
  odeme: 'ödeme',
  odendi: 'ödendi',

  // Yedek Parça Domain
  'Yedek Parca': 'Yedek Parça',
  'Yedek parca': 'Yedek parça',

  // Sıralama / Liste
  Siralama: 'Sıralama',
  siralama: 'sıralama',
  Sekans: 'Sekans', // OK
  Sekanslar: 'Sekanslar', // OK

  // Diğer sık kelimeler
  Varligin: 'Varlığın',
  Varlik: 'Varlık',
  varlik: 'varlık',
  Tum: 'Tüm',
  tum: 'tüm',
  Sureli: 'Süreli',
  suresi: 'süresi',
  Suresi: 'Süresi',
  Goruntule: 'Görüntüle',
  Goruntulemek: 'Görüntülemek',
  goruntule: 'görüntüle',
  Goruntu: 'Görüntü',
  goruntu: 'görüntü',
  Gosterge: 'Gösterge',
  gosterge: 'gösterge',
  Gonder: 'Gönder',
  Coz: 'Çöz',
  coz: 'çöz',
  Cozum: 'Çözüm',
  cozum: 'çözüm',
  Cevir: 'Çevir',
  cevir: 'çevir',
  Cesit: 'Çeşit',
  cesit: 'çeşit',
  Cok: 'Çok',
  cok: 'çok',
  cıkti: 'çıktı',
  cikti: 'çıktı',
  Cikti: 'Çıktı',
  Cikarildi: 'Çıkarıldı',
  cikarildi: 'çıkarıldı',
  Cikis: 'Çıkış',
  cikis: 'çıkış',

  // Takvim / Tarih
  Sub: 'Şub', // Şubat kısaltma
  Subat: 'Şubat',
  subat: 'şubat',

  // Mail / E-posta
  Mailler: 'Mailler', // OK
  Mailleri: 'Mailleri', // OK
  // Emailler already OK

  // Yaygın ASCII-Türkçe fiiller/terimler
  Uygun: 'Uygun', // OK
  Yukle: 'Yükle',
  Yukleniyor: 'Yükleniyor',
  yukle: 'yükle',
  yukleniyor: 'yükleniyor',
  Dusuk: 'Düşük',
  dusuk: 'düşük',
  Yuksek: 'Yüksek',
  yuksek: 'yüksek',
  Orta: 'Orta', // OK

  // "Bir hata olustu" kalıbı
  olustu: 'oluştu',
  Olustu: 'Oluştu',
  olusturuldu: 'oluşturuldu',
  Olusturuldu: 'Oluşturuldu',
  olusturulamadi: 'oluşturulamadı',
  Olusturulamadi: 'Oluşturulamadı',
  olustur: 'oluştur',
  Olustur: 'Oluştur',
  olusturma: 'oluşturma',
  Olusturma: 'Oluşturma',
  olusturan: 'oluşturan',
  Olusturan: 'Oluşturan',

  // Seç / Seçim
  Sec: 'Seç',
  Secim: 'Seçim',
  sec: 'seç',
  secim: 'seçim',
  Secildi: 'Seçildi',
  secildi: 'seçildi',
  Secenek: 'Seçenek',
  secenek: 'seçenek',
  Secilen: 'Seçilen',
  secilen: 'seçilen',

  // Kaydet / Silme
  kaydedildi: 'kaydedildi', // OK
  Kaydedildi: 'Kaydedildi', // OK
  Kaydet: 'Kaydet', // OK

  // Etiketleri olan kelimeler
  Etkilesim: 'Etkileşim',
  etkilesim: 'etkileşim',
  Erisim: 'Erişim',
  erisim: 'erişim',

  // Ana Sayfa / Gelir Kokpiti etc — OK already
  Satis: 'Satış',
  satis: 'satış',
  Satislarim: 'Satışlarım',

  // Kullanıcı
  Kullanici: 'Kullanıcı',
  Kullanicilar: 'Kullanıcılar',
  Kullanicisi: 'Kullanıcısı',
  kullanici: 'kullanıcı',
  kullanicilar: 'kullanıcılar',
  kullanicisi: 'kullanıcısı',

  // Danışman / Koç
  Kocluk: 'Koçluk',
  kocluk: 'koçluk',
  Koc: 'Koç',
  koc: 'koç',

  // Hızlı / Yavaş
  Hizli: 'Hızlı',
  hizli: 'hızlı',
  Hiz: 'Hız',
  hiz: 'hız',

  // Canlı / Sohbet
  Canli: 'Canlı',
  canli: 'canlı',

  // Analitik / Raporlama
  Analitigi: 'Analitiği',
  analitigi: 'analitiği',
  Analitik: 'Analitik', // OK
  analitik: 'analitik', // OK

  // Tahmin / Hedef
  Hedef: 'Hedef', // OK
  hedef: 'hedef', // OK
  Tahmin: 'Tahmin', // OK

  // Fatura / Teklif
  Fatura: 'Fatura', // OK
  Faturalar: 'Faturalar', // OK

  // Kampanya
  Kampanya: 'Kampanya', // OK

  // Abonelik / Gelir
  Abonelik: 'Abonelik', // OK
  Abonelikler: 'Abonelikler', // OK
  Gelir: 'Gelir', // OK
  Gelirler: 'Gelirler', // OK

  // Risk
  Risk: 'Risk', // OK
  Riskli: 'Riskli', // OK

  // Ayarlar / İzinler
  Ayarlar: 'Ayarlar', // OK
  Izinler: 'İzinler',
  Izin: 'İzin',
  izin: 'izin',
  izinler: 'izinler',

  // Entegrasyon
  Entegrasyon: 'Entegrasyon', // OK
  Entegrasyonlar: 'Entegrasyonlar', // OK
};

// ── Dosya tarama ──
const EXCLUDE_DIRS = new Set([
  'node_modules', 'dist', 'build', '.git', 'coverage', '.next',
  '.playwright-mcp', 'dist-electron', '.turbo',
]);

// Skip files that shouldn't be modified
const EXCLUDE_FILES = new Set([
  'i18n.ts', // contains all locale translations, leave alone
  'fix-turkish-chars.mjs', // ourselves
]);

const INCLUDE_EXT = new Set(['.ts', '.tsx', '.js', '.jsx']);

function collectFiles(root, out = []) {
  for (const entry of fs.readdirSync(root, { withFileTypes: true })) {
    const full = path.join(root, entry.name);
    if (entry.isDirectory()) {
      if (EXCLUDE_DIRS.has(entry.name)) continue;
      collectFiles(full, out);
    } else if (entry.isFile()) {
      if (EXCLUDE_FILES.has(entry.name)) continue;
      if (INCLUDE_EXT.has(path.extname(entry.name))) out.push(full);
    }
  }
  return out;
}

// ── Dönüştürme mantığı ──
// Sadece string literal ve JSX text node içindeki kelimeleri dönüştür.
// Identifier'ları, import path'lerini, URL-like stringleri korumak için:
// - Tüm değişiklikleri sadece "..." veya '...' veya `...` içinde yap
// - URL benzeri (/, http://, https://) string'leri atla
// - Kısa (3 char) kelimeleri atla — false positive riski yüksek

const URL_PATTERN = /^(https?:\/\/|\/[a-z0-9\-_]|mailto:|tel:)/i;
const IMPORT_PATH_HINT = /^[./@][\w\-/@.]+$/;

function shouldSkipString(str) {
  if (str.length < 3) return true;
  if (URL_PATTERN.test(str)) return true;
  if (IMPORT_PATH_HINT.test(str)) return true;
  return false;
}

/** Kelime sınırlı değiştirme — sadece word boundary'de eşleşir */
function transformStringContent(content) {
  let changed = false;
  let result = content;
  // Sort keys by length DESC so multi-word like "Yedek Parca" matches before "Parca"
  const keys = Object.keys(WORD_MAP).sort((a, b) => b.length - a.length);
  for (const key of keys) {
    const val = WORD_MAP[key];
    if (key === val) continue; // no-op
    // Word-boundary regex — escape special chars
    const escaped = key.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    const re = new RegExp(`(?<![A-Za-zÇĞİÖŞÜçğıöşü_0-9])${escaped}(?![A-Za-zÇĞİÖŞÜçğıöşü_0-9])`, 'g');
    const before = result;
    result = result.replace(re, val);
    if (before !== result) changed = true;
  }
  return { result, changed };
}

/** Regex-based string literal finder and transformer. No AST dependency. */
function transformFile(content) {
  let changed = false;
  let result = '';
  let i = 0;
  const len = content.length;

  while (i < len) {
    const ch = content[i];
    const prev = i > 0 ? content[i - 1] : '';

    // Block comment /* ... */
    if (ch === '/' && content[i + 1] === '*') {
      const end = content.indexOf('*/', i + 2);
      const segment = end === -1 ? content.slice(i) : content.slice(i, end + 2);
      result += segment;
      i += segment.length;
      continue;
    }

    // Line comment // ...
    if (ch === '/' && content[i + 1] === '/') {
      const end = content.indexOf('\n', i);
      const segment = end === -1 ? content.slice(i) : content.slice(i, end);
      result += segment;
      i += segment.length;
      continue;
    }

    // String literal with ', ", or `
    if ((ch === "'" || ch === '"' || ch === '`') && prev !== '\\') {
      const quote = ch;
      let j = i + 1;
      // For backticks, could contain ${} but we don't evaluate - just find matching backtick
      while (j < len) {
        if (content[j] === '\\') { j += 2; continue; }
        if (content[j] === quote) break;
        j++;
      }
      const raw = content.slice(i + 1, j);
      // Transform
      let transformed = raw;
      if (!shouldSkipString(raw)) {
        const r = transformStringContent(raw);
        if (r.changed) {
          transformed = r.result;
          changed = true;
        }
      }
      result += quote + transformed + quote;
      i = j + 1;
      continue;
    }

    // JSX text: > text <
    // Simpler heuristic: detect `>` followed by non-tag content up to `<`
    // Risky with JSX expressions {expr} and operators. Skip — most UI text
    // is already in string props.

    result += ch;
    i++;
  }

  return { result, changed };
}

// ── Main ──
const args = process.argv.slice(2);
const dryRun = args.includes('--dry-run');
const rootArg = args.find((a, idx) => args[idx - 1] === '--root');
const ROOT = path.resolve(__dirname, '..', rootArg || 'frontend/src');

if (!fs.existsSync(ROOT)) {
  console.error(`Root not found: ${ROOT}`);
  process.exit(1);
}

const files = collectFiles(ROOT);
console.log(`Scanning ${files.length} files in ${ROOT}...`);

let totalChanged = 0;
let totalFiles = 0;
const changedFiles = [];

for (const file of files) {
  const content = fs.readFileSync(file, 'utf8');
  const { result, changed } = transformFile(content);
  if (changed) {
    totalFiles++;
    // Count occurrences changed
    const diffLines = content.split('\n').length - result.split('\n').length;
    changedFiles.push({ file: path.relative(ROOT, file), diffLines });
    if (!dryRun) {
      fs.writeFileSync(file, result, 'utf8');
    }
    totalChanged++;
  }
}

console.log(`\n${dryRun ? '[DRY RUN] Would change' : 'Changed'} ${totalFiles} files:`);
for (const { file } of changedFiles.slice(0, 50)) {
  console.log(`  ${file}`);
}
if (changedFiles.length > 50) {
  console.log(`  ... and ${changedFiles.length - 50} more`);
}

if (dryRun) {
  console.log('\nRun without --dry-run to apply.');
}
