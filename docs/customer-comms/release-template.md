# Feature Release — Turkish Template

Use when a feature behind a `FEATURE_*` flag is being enabled in
production, especially when it changes a workflow customers were
already using. Pure additive features (a new admin-only report)
don't need this.

Send 1-3 days BEFORE flipping the flag for power users; on the
day-of for everyone else.

---

**Konu:** Honeywell Sales Suite — Yeni Özellik: [FEATURE_NAME]

Merhaba [CUSTOMER_NAME],

[ROLLOUT_DATE] tarihinden itibaren **[FEATURE_NAME]** özelliği
hesabınızda kullanıma açılacaktır.

**Ne işe yarıyor:**
[ONE_PARAGRAPH — özellik ne yapıyor, hangi işi kolaylaştırıyor.
Pazarlama dili değil; "şu butona tıkladığınızda şu şeyin olması"
seviyesinde somut.]

**Sizin için ne değişiyor:**
- [BEFORE / AFTER — örn. "Daha önce manuel girdiğiniz X bilgisi,
  artık [SOURCE]'tan otomatik çekilecek."]
- [BEFORE / AFTER — başka bir somut değişiklik]
- [WORKFLOW_NOTE — eski akış hâlâ çalışıyor mu, yoksa migration
  gerekli mi?]

**Yapmanız gereken:**
1. [STEP_1 — örn. "Settings → [FEATURE_NAME] sayfasından entegrasyonu
   doğrulayın."]
2. [STEP_2 — örn. "Var olan teklifleriniz değişmeyecek; ancak yeni
   oluşturduğunuz teklifler bu yeni akışı kullanacak."]
3. [STEP_3 — örn. "Geri bildiriminiz için [CONTACT_CHANNEL]
   üzerinden bizimle iletişime geçebilirsiniz."]

**Eğer kullanmak istemezseniz:**
[ROLLBACK_INSTRUCTIONS — örn. "Settings → Features bölümünden
özelliği kapatabilirsiniz" veya "Hesap yöneticinize kapatmasını
söyleyebilirsiniz". Eğer flag kapatılamazsa, "Şu an opt-out yok,
ancak [ALTERNATIVE_WORKFLOW] kullanmaya devam edebilirsiniz."]

**Detaylı dokümantasyon:** [DOCS_LINK]
**Demo videosu:** [VIDEO_LINK — varsa]

Sorularınız için her zaman buradayız.

İyi çalışmalar,
[YOUR_NAME]
Honeywell Sales Suite Ekibi

---

## Internal checklist

- [ ] Feature staging'de ≥48 saat sorunsuz çalıştı mı?
- [ ] Documentation sayfası canlıda mı?
- [ ] Hesap yöneticileri (account managers) bilgilendirildi mi?
- [ ] Müşteri-ulaşılabilir destek kanalı belli mi?
- [ ] Rollback yolu (flag → false) test edildi mi?
- [ ] Tüm `[BRACKETED]` alanlar dolduruldu mu?
