import { useState } from 'react'
import { StatusBadge } from '@/components/common/StatusBadge'
import { JsonViewer } from '@/components/common/JsonViewer'
import { checkLabel, documentLabel } from '@/lib/validationLabels'
import { cn } from '@/lib/utils'
import type { ValidationResultOut } from '@/schemas/validation.schema'

interface ValidationRowProps {
  result: ValidationResultOut
}

// evidence is an open-ended record, so every read has to tolerate a missing
// or non-string value rather than trusting the shape.
function readString(evidence: Record<string, unknown> | null, key: string): string | null {
  const value = evidence?.[key]
  if (value === undefined || value === null || value === '') return null
  return typeof value === 'string' ? value : String(value)
}

interface ValueCardProps {
  title: string
  document: string | null
  value: string | null
}

function ValueCard({ title, document, value }: ValueCardProps) {
  return (
    <div className="flex-1 rounded-lg border border-slate-200 bg-white px-3 py-2">
      <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">
        {title} · <span className="normal-case">{documentLabel(document)}</span>
      </div>
      <div className="mt-1 break-words text-sm text-slate-900">{value ?? '—'}</div>
    </div>
  )
}

export function ValidationRow({ result }: ValidationRowProps) {
  const [expanded, setExpanded] = useState(false)
  const evidence = result.evidence ?? null

  // Results saved before evidence carried these keys fall back to the
  // document the result is attributed to, and a generic message.
  const sourceDocument = readString(evidence, 'source_document') ?? result.document_id ?? null
  const targetDocument = readString(evidence, 'target_document')
  const message =
    readString(evidence, 'message') ?? (result.passed ? 'Check passed.' : 'Check failed.')

  return (
    <>
      <tr className="transition-colors hover:bg-slate-50">
        <td className="px-4 py-3 text-sm font-medium text-slate-900">
          {checkLabel(result.check_type)}
        </td>
        <td className="px-4 py-3 text-sm text-slate-700">{documentLabel(sourceDocument)}</td>
        <td className="px-4 py-3 text-sm text-slate-700">{documentLabel(targetDocument)}</td>
        <td className="px-4 py-3 text-sm text-slate-700">{result.score.toFixed(1)}</td>
        <td className="px-4 py-3">
          <StatusBadge status={result.passed ? 'PASS' : 'FAIL'} />
        </td>
        <td className="px-4 py-3 text-right">
          <button
            type="button"
            onClick={() => setExpanded((e) => !e)}
            aria-expanded={expanded}
            className="text-xs font-medium text-brand-600 hover:text-brand-800 hover:underline"
          >
            {expanded ? 'Hide details' : 'View details'}
          </button>
        </td>
      </tr>
      {expanded && (
        <tr className="bg-slate-50">
          <td colSpan={6} className="space-y-3 px-4 py-4">
            <p
              className={cn(
                'rounded-lg border px-3 py-2 text-sm',
                result.passed
                  ? 'border-emerald-200 bg-emerald-50 text-emerald-800'
                  : 'border-red-200 bg-red-50 text-red-800'
              )}
            >
              {message}
            </p>
            {(sourceDocument || targetDocument) && (
              <div className="flex flex-col gap-3 sm:flex-row">
                <ValueCard
                  title="Source"
                  document={sourceDocument}
                  value={readString(evidence, 'source_value')}
                />
                <ValueCard
                  title="Target"
                  document={targetDocument}
                  value={readString(evidence, 'target_value')}
                />
              </div>
            )}
            {/* Kept for debugging; collapsed so it doesn't compete with the summary. */}
            <details className="text-xs text-slate-600">
              <summary className="cursor-pointer select-none font-medium text-slate-700">
                Raw evidence
              </summary>
              <div className="mt-2">
                <JsonViewer data={evidence ?? {}} />
              </div>
            </details>
          </td>
        </tr>
      )}
    </>
  )
}
