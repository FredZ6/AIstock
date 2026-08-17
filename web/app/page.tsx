export default function Home() {
  return (
    <main className="mx-auto flex min-h-screen max-w-4xl flex-col justify-center gap-6 px-8">
      <span className="w-fit rounded-full border border-emerald-500 px-3 py-1 text-sm text-emerald-300">
        Fixture Mode
      </span>
      <h1 className="text-4xl font-semibold">AI Agent 美股科技研究与模拟投资平台</h1>
      <p className="max-w-2xl text-zinc-400">
        Evidence-grounded research and paper-trading simulation. No provider credential or live
        brokerage connection is enabled.
      </p>
    </main>
  )
}
