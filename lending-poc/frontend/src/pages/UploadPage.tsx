import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAppStore, type DocType, type UploadedDocument } from '@/store/useAppStore'
import { DOCUMENT_TYPE_CONFIG, isAcceptedFileType, MAX_FILE_SIZE_BYTES, MAX_FILE_SIZE_MB } from '@/lib/documentTypes'
import { DocumentUploadCard } from '@/components/upload/DocumentUploadCard'
import { UploadSummary } from '@/components/upload/UploadSummary'
import { Button } from '@/components/common/Button'
import {
  buildMockFieldMappingResults,
  buildMockOcrResults,
  buildMockTranslationResults,
  buildMockUploadedDocuments,
  MOCK_VALIDATION_RESULT,
} from '@/lib/mockWorkflowData'

function makeDocumentId(docType: DocType, file: File): string {
  return `${docType}-${file.name}-${file.size}-${file.lastModified}`
}

export default function UploadPage() {
  const navigate = useNavigate()
  const uploadedDocuments = useAppStore((s) => s.uploadedDocuments)
  const setUploadedDocuments = useAppStore((s) => s.setUploadedDocuments)
  const setCurrentStep = useAppStore((s) => s.setCurrentStep)
  const resetWorkflow = useAppStore((s) => s.resetWorkflow)
  const setOcrResults = useAppStore((s) => s.setOcrResults)
  const setTranslationResults = useAppStore((s) => s.setTranslationResults)
  const setFieldMappingResults = useAppStore((s) => s.setFieldMappingResults)
  const setValidationResult = useAppStore((s) => s.setValidationResult)

  const [errors, setErrors] = useState<Partial<Record<DocType, string>>>({})

  const documentsByType = useMemo(() => {
    const map: Partial<Record<DocType, UploadedDocument>> = {}
    uploadedDocuments.forEach((doc) => {
      map[doc.docType] = doc
    })
    return map
  }, [uploadedDocuments])

  const handleSelect = (docType: DocType, file: File) => {
    if (!isAcceptedFileType(file)) {
      setErrors((prev) => ({ ...prev, [docType]: 'Unsupported file type. Use PDF, PNG, or JPG.' }))
      return
    }
    if (file.size > MAX_FILE_SIZE_BYTES) {
      setErrors((prev) => ({ ...prev, [docType]: `File exceeds the ${MAX_FILE_SIZE_MB}MB size limit.` }))
      return
    }
    setErrors((prev) => ({ ...prev, [docType]: undefined }))

    const newDoc: UploadedDocument = {
      id: makeDocumentId(docType, file),
      docType,
      file,
      fileName: file.name,
      fileSize: file.size,
      fileType: file.type || file.name.split('.').pop() || '',
    }
    const next = uploadedDocuments.filter((d) => d.docType !== docType)
    next.push(newDoc)
    setUploadedDocuments(next)
  }

  const handleRemove = (docType: DocType) => {
    setUploadedDocuments(uploadedDocuments.filter((d) => d.docType !== docType))
  }

  const allUploaded = DOCUMENT_TYPE_CONFIG.every((c) => documentsByType[c.docType])

  const handleProceed = () => {
    // Fresh run: clear any stale downstream results from a previous session,
    // then restore the documents the user just selected.
    const docs = uploadedDocuments
    resetWorkflow()
    setUploadedDocuments(docs)
    setCurrentStep('processing')
    navigate('/processing')
  }

  // TEMPORARY (UI review only): seeds every workflow stage with mock data so
  // Field Mapping and Validation can be reviewed without live backends.
  // Remove this handler and the button below once real data flows end-to-end.
  const handleLoadMockData = () => {
    resetWorkflow()
    const docs = buildMockUploadedDocuments()
    setUploadedDocuments(docs)
    setOcrResults(buildMockOcrResults(docs))
    setTranslationResults(buildMockTranslationResults(docs))
    setFieldMappingResults(buildMockFieldMappingResults(docs))
    setValidationResult(MOCK_VALIDATION_RESULT, MOCK_VALIDATION_RESULT.applicant_ref)
    setCurrentStep('validation')
    navigate('/validation')
  }

  const groups = ['Identity Documents', 'Financial Documents'] as const

  return (
    <div className="space-y-8">
      <div>
        <h2 className="text-2xl font-semibold tracking-tight text-slate-900">Upload Documents</h2>
        <p className="mt-1.5 text-sm text-slate-600">
          Upload all four required documents to begin verification. Nothing is sent to the server
          until you click Start Verification.
        </p>
      </div>

      {import.meta.env.DEV && (
        <div className="flex items-center justify-between gap-4 rounded-xl border border-dashed border-amber-300 bg-amber-50 p-4">
          <p className="text-xs text-amber-800">
            Dev only — seeds every workflow step with mock data so the UI can be reviewed without
            running backends. Remove before shipping.
          </p>
          <Button
            type="button"
            onClick={handleLoadMockData}
            className="shrink-0 bg-amber-600 hover:bg-amber-700 focus-visible:ring-amber-500"
          >
            Load Mock Data
          </Button>
        </div>
      )}

      {groups.map((group) => (
        <div key={group}>
          <h3 className="mb-3 text-xs font-semibold uppercase tracking-wide text-slate-500">
            {group}
          </h3>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            {DOCUMENT_TYPE_CONFIG.filter((c) => c.group === group).map((config) => (
              <DocumentUploadCard
                key={config.docType}
                label={config.label}
                document={documentsByType[config.docType]}
                error={errors[config.docType]}
                onSelect={(file) => handleSelect(config.docType, file)}
                onRemove={() => handleRemove(config.docType)}
              />
            ))}
          </div>
        </div>
      ))}

      <div className="flex items-center justify-between border-t border-slate-200 pt-6">
        <UploadSummary documents={documentsByType} />
        <Button type="button" disabled={!allUploaded} onClick={handleProceed}>
          Start Verification →
        </Button>
      </div>
    </div>
  )
}
