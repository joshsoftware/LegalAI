import { ValidationRow } from './ValidationRow'
import type { ValidationResultOut } from '@/schemas/validation.schema'

interface ValidationTableProps {
  results: ValidationResultOut[]
}

export function ValidationTable({ results }: ValidationTableProps) {
  return (
    <div className="overflow-hidden overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-card">
      <table className="min-w-full divide-y divide-slate-200">
        <thead className="bg-slate-50">
          <tr>
            <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">
              Check
            </th>
            <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">
              Source
            </th>
            <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">
              Target
            </th>
            <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">
              Confidence Score
            </th>
            <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">
              Status
            </th>
            <th className="px-4 py-3" />
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {results.map((result, index) => (
            // check_type/document_id are not guaranteed unique across rows,
            // so the index is included to keep the composite key stable.
            <ValidationRow
              key={`${result.check_type}-${result.document_id ?? ''}-${index}`}
              result={result}
            />
          ))}
        </tbody>
      </table>
    </div>
  )
}
