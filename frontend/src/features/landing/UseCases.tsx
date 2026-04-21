import { useMemo } from 'react';
import { motion } from 'framer-motion';
import { Zap, Eye, Database, type LucideIcon } from 'lucide-react';
import { useT } from '../../hooks/useT';
import type { TranslationKey } from '../../lib/i18n';

type Persona = {
  icon: LucideIcon;
  roleKey: TranslationKey;
  headlineKey: TranslationKey;
  bulletKeys: TranslationKey[];
  color: string;
  iconColor: string;
};

export default function UseCases() {
  const t = useT();

  const personas: Persona[] = useMemo(
    () => [
      {
        icon: Zap,
        roleKey: 'landing.uc_rep_role',
        headlineKey: 'landing.uc_rep_head',
        bulletKeys: ['landing.uc_rep_b1', 'landing.uc_rep_b2', 'landing.uc_rep_b3'],
        color: 'border-blue-200 bg-blue-50',
        iconColor: 'bg-blue-600',
      },
      {
        icon: Eye,
        roleKey: 'landing.uc_mgr_role',
        headlineKey: 'landing.uc_mgr_head',
        bulletKeys: ['landing.uc_mgr_b1', 'landing.uc_mgr_b2', 'landing.uc_mgr_b3'],
        color: 'border-violet-200 bg-violet-50',
        iconColor: 'bg-violet-600',
      },
      {
        icon: Database,
        roleKey: 'landing.uc_ops_role',
        headlineKey: 'landing.uc_ops_head',
        bulletKeys: ['landing.uc_ops_b1', 'landing.uc_ops_b2', 'landing.uc_ops_b3'],
        color: 'border-emerald-200 bg-emerald-50',
        iconColor: 'bg-emerald-600',
      },
    ],
    [],
  );

  return (
    <section className="bg-slate-50 py-20 md:py-28">
      <div className="mx-auto max-w-7xl px-6">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          className="mx-auto max-w-2xl text-center"
        >
          <p className="text-xs font-semibold uppercase tracking-widest text-slate-500">
            {t('landing.usecases_label')}
          </p>
          <h2 className="mt-3 text-3xl font-bold tracking-tight text-slate-900 md:text-4xl">
            {t('landing.usecases_title')}
          </h2>
        </motion.div>

        <div className="mt-14 grid grid-cols-1 gap-6 md:grid-cols-3">
          {personas.map((p, i) => {
            const PIcon = p.icon;
            return (
              <motion.div
                key={p.roleKey}
                initial={{ opacity: 0, y: 30 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true }}
                transition={{ delay: i * 0.12 }}
                className={`rounded-2xl border p-7 ${p.color}`}
              >
                <div
                  className={`mb-4 inline-flex h-10 w-10 items-center justify-center rounded-xl text-white ${p.iconColor}`}
                >
                  <PIcon size={18} />
                </div>
                <p className="text-xs font-bold uppercase tracking-widest text-slate-500">
                  {t(p.roleKey)}
                </p>
                <h3 className="mt-2 text-lg font-bold text-slate-900">{t(p.headlineKey)}</h3>
                <ul className="mt-4 space-y-2">
                  {p.bulletKeys.map((bk) => (
                    <li key={bk} className="flex items-start gap-2 text-sm text-slate-700">
                      <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-slate-400" />
                      {t(bk)}
                    </li>
                  ))}
                </ul>
              </motion.div>
            );
          })}
        </div>
      </div>
    </section>
  );
}
