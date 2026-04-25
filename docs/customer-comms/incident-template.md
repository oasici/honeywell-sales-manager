# Incident Notification — Turkish Template

Use for SEV1 / SEV2 outages where customers experienced a
visible degradation. Send AFTER recovery, not during — the
on-call team should focus on the fix, not the messaging.

For SEV1: send within 4 hours of recovery.
For SEV2: send within 24 hours, or skip if impact was bounded
to a small user set who already saw the workaround banner.

---

**Konu:** Honeywell Sales Suite — Servis Kesintisi Bildirimi ([DATE])

Merhaba [CUSTOMER_NAME],

[DATE] tarihinde [START_TIME] – [END_TIME] saatleri arasında, toplamda
yaklaşık **[DURATION]** süreyle servisimizde kesinti yaşanmıştır.

**Etkilenen bileşen:** [COMPONENT — örn. "Teklif oluşturma akışı",
"AI özet endpoint'i", "tüm yazma operasyonları"]

**Kök sebep:** [ROOT_CAUSE — bir paragraf, teknik jargon olmadan.
Örn. "Bir veritabanı yapılandırma değişikliği bağlantı havuzunu
beklenmedik şekilde tüketti ve istekler timeout almaya başladı."]

**Alınan önlemler:**
1. [MITIGATION_1 — örn. "Yapılandırma anlık olarak geri alındı."]
2. [MITIGATION_2 — örn. "Bağlantı havuzu boyutu CI'a sabit testle
   gate'lendi."]
3. [MITIGATION_3 — örn. "Sentry'de erken uyarı için yeni bir alarm
   kuralı eklendi."]

**Sizin için ne anlama geliyor:**
- Bu süre boyunca [SPECIFIC_ACTION — örn. "kaydedilen değişiklikler",
  "gönderilen email'ler"] etkilenmiştir.
- [DATA_INTEGRITY_NOTE — örn. "Veri kaybı yaşanmamıştır" veya "[N]
  müşteriden gelen webform isteği yeniden işlenmiştir"]
- [CUSTOMER_ACTION — eğer varsa, müşterinin yapması gereken bir şey.
  Yoksa "Ek bir aksiyon almanıza gerek yoktur."]

**Detaylı post-mortem raporumuz** [DATE+7] tarihinde Slack
kanalınızda paylaşılacaktır. Sorularınız için doğrudan benimle veya
hesap yöneticinizle iletişime geçebilirsiniz.

Yaşadığınız olumsuzluk için özür diler, sabrınız için teşekkür ederiz.

İyi çalışmalar,
[YOUR_NAME]
[YOUR_ROLE], Honeywell Sales Suite
[YOUR_EMAIL]

---

## Slug çekirdek

Daha kısa bir Slack/in-app banner versiyonu için:

> [START_TIME]–[END_TIME] arası [COMPONENT] kesinti yaşandı, sebep
> [ROOT_CAUSE_SHORT]. Veri kaybı yok. Detaylı rapor [DATE+7]'de.

## Internal checklist (göndermeden önce)

- [ ] Postmortem hazır mı? (`docs/postmortems/YYYY-MM-DD-{slug}.md`)
- [ ] Aksiyon maddeleri owner ve due-date içeriyor mu?
- [ ] Hukuk gerekli mi? (PII / KVKK boyutu varsa evet)
- [ ] Tüm `[BRACKETED]` alanlar dolduruldu mu?
- [ ] İkinci bir okuyucu onayladı mı?
- [ ] Send timestamp + alıcı listesi audit log'a yazıldı mı?
