# Türkçe Karakter Kullanım Kuralları

Bu proje tek dilli (Türkçe) bir arayüz sunar. UI metinleri **mutlaka** doğru Türkçe karakterler kullanılarak yazılmalıdır.

## Kural

### ✅ Doğru

```tsx
<h1>Müşteri Bilgileri</h1>
<Button>Fırsat Oluştur</Button>
<Badge>Ayrıştırıldı</Badge>
toast.success('İş kuralı güncellendi');
```

### ❌ Yanlış

```tsx
<h1>Musteri Bilgileri</h1>       {/* ş, ü eksik */}
<Button>Firsat Olustur</Button>  {/* ı, ş eksik */}
<Badge>Ayristirildi</Badge>      {/* ı, ş eksik */}
toast.success('Is kurali guncellendi');
```

## Kısıtlar

Bu kural **sadece görünür UI metinleri** için geçerlidir:
- JSX text (`<div>Müşteri</div>`)
- String prop (`<Badge label="Fırsat" />`)
- Toast/error mesajları
- Placeholder metinleri
- i18n dictionary değerleri

Şunlar **ASCII kalabilir**:
- Kod identifier'ları: `customerId`, `spareParts`, `yedekParcaItems`
- Type/interface adları: `Customer`, `Opportunity`
- HTTP rotaları: `/api/v1/customers`
- localStorage anahtarları: `sidebar-yedek-parca-collapsed`
- URL slug'ları: `customers`, `opportunities`
- Import path'leri
- Kod yorumları (`// Kocluk - manager only`) — tercihen doğru yazın ama engellenmez
- Brand/marka isimleri

## Sıralama ve Arama

Türkçe karakterler için `localeCompare` kullanırken `'tr'` locale belirtin:

```typescript
import { TR_COLLATOR, toLowerTR } from './lib/formatters';

// Doğru
items.sort((a, b) => TR_COLLATOR.compare(a.name, b.name));

// Arama için Türkçe-güvenli lowercase
if (toLowerTR(item.name).includes(toLowerTR(searchTerm))) { ... }

// Yanlış: "İstanbul".toLowerCase() → "i̇stanbul" (i̇ nokta üzerine nokta)
```

## Yardımcı Script'ler

### Tarama

```bash
# Tüm kodu tara, uyarı listesi
cd frontend && npm run lint:turkish

# CI için (hata varsa exit 1)
cd frontend && npm run lint:turkish:strict

# Sadece staged dosyaları tara (pre-commit için)
cd frontend && npm run lint:turkish:staged
```

### Toplu Dönüşüm

Mevcut kodu düzeltmek için:

```bash
# Dry run — değişiklikleri göster
node scripts/fix-turkish-chars.mjs --dry-run

# Uygula
node scripts/fix-turkish-chars.mjs
```

Bu script sadece string literal içinde (tırnak içinde) kelimeleri dönüştürür,
identifier'lara dokunmaz. Backtick template literal içindeki nested string'lerde
dikkatli olun — script bunlarda bozulabilir.

## Pre-commit Hook (Opsiyonel)

`husky` veya `lefthook` ile kuralı zorlamak için:

```bash
# .husky/pre-commit
cd frontend && npm run lint:turkish:staged || exit 1
```

## Yeni Kelime Ekleme

`scripts/lint-turkish.mjs` içindeki `ASCII_TURKISH_WORDS` dizisine yeni kelime
ekleyebilirsiniz. Hem uppercase hem lowercase formu ekleyin.

## Karakter Cetveli

| ASCII | Türkçe | Örnek |
|-------|--------|-------|
| `s` | `ş` | Müşteri, Şirket |
| `c` | `ç` | Çözüm, Geçerli |
| `g` | `ğ` | Sağlık, Aşağı |
| `i` | `ı` | Açıklama, Tanım |
| `I` | `İ` | İşlem, İptal |
| `o` | `ö` | Görüşme, Öneri |
| `u` | `ü` | Müşteri, Düzenle |

Not: Türkçe `ı` ve `İ` İngilizce `i/I`'den farklıdır. `I` (büyük I) ASCII'de
noktasızdır, Türkçe'de `İ` (noktalı) ve `I` (noktasız) ayrı harflerdir.
