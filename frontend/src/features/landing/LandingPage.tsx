import { lazy, Suspense } from 'react';

const Navbar = lazy(() => import('./Navbar'));
const Hero = lazy(() => import('./Hero'));
const Problem = lazy(() => import('./Problem'));
const Solution = lazy(() => import('./Solution'));
const Features = lazy(() => import('./Features'));
const Proof = lazy(() => import('./Proof'));
const UseCases = lazy(() => import('./UseCases'));
const Pricing = lazy(() => import('./Pricing'));
const FAQ = lazy(() => import('./FAQ'));
const FinalCTA = lazy(() => import('./FinalCTA'));
const Footer = lazy(() => import('./Footer'));

export default function LandingPage() {
  return (
    <div className="min-h-screen bg-slate-50 text-slate-900 antialiased">
      <Suspense fallback={null}>
        <Navbar />
        <Hero />
        <Problem />
        <Solution />
        <Features />
        <Proof />
        <UseCases />
        <Pricing />
        <FAQ />
        <FinalCTA />
        <Footer />
      </Suspense>
    </div>
  );
}
