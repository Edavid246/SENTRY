import { clearanceStyle } from "@/lib/clearance";

export function ClearanceBadge({ code, large = false }: { code: string | null; large?: boolean }) {
  const style = clearanceStyle(code);
  return (
    <span
      className={`inline-block border font-medium uppercase tracking-[0.1em] ${style.className} ${
        large ? "px-3 py-1 text-[1.15rem]" : "px-2 py-0.5 text-[0.75rem]"
      }`}
    >
      {style.label}
    </span>
  );
}
