# Security Disclosure — Turkish Template

Use for vulnerabilities, account compromises, or exposed PII. KVKK
notification requirements may also apply — coordinate with the data
protection officer (DPO) BEFORE drafting customer-facing content.

Legal review is mandatory for any communication that touches:
- Personal data exposure (KVKK Article 12 — 72-hour notification clock)
- Authentication compromise (passwords, tokens, session hijacking)
- Third-party CVE that we haven't yet patched

The DPO and legal counsel sign off before send. Don't shortcut this.

---

**Konu:** [GUVENLIK / VERI ISLEM] Bildirimi — Honeywell Sales Suite

Sayın [CUSTOMER_NAME],

[INCIDENT_DATE] tarihinde tespit ettiğimiz bir güvenlik konusu
hakkında sizi şeffaflıkla bilgilendirmek isteriz.

**Ne oldu:**
[ONE_PARAGRAPH_FACTUAL — ne tespit edildi, ne zaman gerçekleşti,
ne zaman tespit edildi. Belirsiz dil kullanma. "Şüpheleniyoruz"
yerine "Tespit ettik" veya "Henüz teyit edemedik" — net konuş.]

**Etkilenen veri:**
- [DATA_TYPE_1 — örn. "Kullanıcı email adresleri ve isim alanları"]
- [DATA_TYPE_2 — örn. "Şifreler etkilenmemiştir; bcrypt hash'i ile
  saklanmaktadır"]
- [DATA_TYPE_3 — örn. "[N] kayıt etkilenmiş olabilir"]

**Etkilenen müşteriler:**
[SCOPE_DESCRIPTION — örn. "Sadece [DATE_RANGE] arasında hesap
oluşturan [N] kullanıcı" veya "Tüm aktif kullanıcılar"]

**Aldığımız önlemler:**
1. [REMEDIATION_1 — örn. "Açık olan endpoint kapatıldı."]
2. [REMEDIATION_2 — örn. "Tüm kullanıcı oturumları sıfırlandı,
   yeniden giriş yapmanız gerekecektir."]
3. [REMEDIATION_3 — örn. "Bağımsız güvenlik denetçisi ile inceleme
   başlatıldı."]
4. [REMEDIATION_4 — örn. "KVK Kurulu'na 72 saat içinde bildirim
   yapılmıştır."]

**Sizin yapmanız gerekenler:**
1. [USER_ACTION_1 — örn. "Şifrenizi değiştirin. Aynı şifreyi başka
   bir serviste kullanıyorsanız orada da değiştirin."]
2. [USER_ACTION_2 — örn. "Hesap aktivitesi raporunuzu inceleyin."]
3. [USER_ACTION_3 — örn. "Şüpheli bir email/SMS aldıysanız tıklamayın,
   bize iletin."]

**KVKK Hakları:**
6698 sayılı KVKK kapsamındaki haklarınızı (verilerinize erişim, silme
talebi, vb.) [CONTACT_EMAIL] adresinden talep edebilirsiniz. Bizden
veri işlem kayıtlarınızı isteme hakkınız da bulunmaktadır.

**İletişim:**
- Genel sorular: [SUPPORT_EMAIL]
- KVKK / Veri sorumlusu: [DPO_EMAIL]
- Resmi posta: [LEGAL_ADDRESS]

Yaşadığınız endişe için özür dileriz. Detaylı bilgilendirme ve
takip raporumuz [FOLLOW_UP_DATE] tarihine kadar tarafınıza
ulaştırılacaktır.

Saygılarımızla,
[CISO_NAME]
[CISO_TITLE]
Honeywell Sales Suite

---

## Internal checklist (göndermeden önce)

- [ ] **DPO (Veri Sorumlusu) imzaladı mı?** — Zorunlu.
- [ ] **Hukuk imzaladı mı?** — Zorunlu.
- [ ] KVK Kurulu bildirimi yapıldı mı? (72 saat penceresi açıksa)
- [ ] Yetkililer (CTO, CISO) bilgilendirildi mi?
- [ ] Postmortem (`docs/postmortems/`) hazır mı?
- [ ] Etkilenen kullanıcı listesi `audit_logs` ile cross-check edildi mi?
- [ ] Şifreler / token'lar rotate edildi mi?
- [ ] Press / PR briefingi gerekli mi? (büyük scope ise evet)
- [ ] Müşteri destek ekibi script'le donatıldı mı? (gelen aramalar için)
- [ ] Tüm `[BRACKETED]` alanlar dolduruldu mu?

## Send mechanics

- Email — toplu transactional kanal (SMTP_FROM_ADDRESS).
- Slack/Teams — eğer entegre customer success kanalı varsa.
- In-app banner — login sonrası modal, "Anladım" tıklayana kadar
  kalıcı.
- Press release — sadece scope > 1000 kayıt veya CISO kararı varsa.

## What NOT to write

- "Bilgisayar korsanı saldırısı" gibi sansasyonel dil — yanlış da
  olabilir, hukuk problemi de yaratır.
- "Hiçbir veri etkilenmedi" — eğer kanıtlanamıyorsa söyleme.
- "Önemsiz" / "küçük" — etki seviyesini hafifletme; müşteri kendi
  karar versin.
- Komple saldırı vektörünü — ayrıntılı teknik detay düşmana yardım eder.
