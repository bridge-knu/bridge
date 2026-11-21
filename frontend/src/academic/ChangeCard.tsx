import { admissionTargetText, formatEffectiveDate, isAdmissionSpecific, type AcademicChange } from './changes.ts'

/** 타임라인의 변경 항목 하나. 내 입학년도만 대상인 항목은 강조한다. */
export default function ChangeCard({ change }: { change: AcademicChange }) {
  const specific = isAdmissionSpecific(change)
  return (
    <article className={`academic-change${specific ? ' mine' : ''}`}>
      <header className="academic-change-meta">
        <time dateTime={change.effectiveDate}>{formatEffectiveDate(change.effectiveDate)} 시행</time>
        <span className={`academic-badge${specific ? ' mine' : ''}`}>
          {specific ? `내 학번 대상 · ${admissionTargetText(change)}` : '전체 학번 대상'}
        </span>
      </header>
      <h3>{change.title}</h3>
      <p>{change.summary}</p>
      <a href={change.sourceUrl} target="_blank" rel="noopener noreferrer" className="academic-source">
        공식 공지 보기 (새 탭)
      </a>
    </article>
  )
}
