import Link from "next/link";
import type { ResultTable } from "@/lib/api";

function cell(value: unknown): string {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "boolean") return value ? "yes" : "no";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

export function ResultTableView({ table }: { table: ResultTable }) {
  return (
    <div data-testid="result-table" className="mt-4 overflow-x-auto border border-rule">
      <table className="w-full border-collapse text-left text-[0.85rem]">
        <thead>
          <tr className="border-b border-rule bg-raised">
            {table.columns.map((c) => (
              <th key={c} className="label whitespace-nowrap px-3 py-2 font-medium">
                {c.replaceAll("_", " ")}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {table.rows.map((row, i) => (
            <tr key={i} className="border-b border-rule/60 last:border-0">
              {table.columns.map((c) => (
                <td key={c} className="whitespace-nowrap px-3 py-2">
                  {c === "id" && typeof row[c] === "string" ? (
                    <Link
                      href={`/${(row[c] as string).startsWith("FND-") ? "findings" : "records"}/${encodeURIComponent(row[c] as string)}`}
                      data-testid="record-link"
                      className="font-mono text-amber hover:underline"
                    >
                      {row[c] as string}
                    </Link>
                  ) : (
                    cell(row[c])
                  )}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      <div className="border-t border-rule px-3 py-1.5 text-[0.75rem] text-mute">
        {table.rows.length} {table.rows.length === 1 ? "row" : "rows"} · typed query, read-only
      </div>
    </div>
  );
}
