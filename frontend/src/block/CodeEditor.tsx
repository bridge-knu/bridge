// Monaco 에디터. 무거워서 BlockPage가 React.lazy로 따로 불러온다.
// CDN을 쓰지 않고 번들에 넣는다 (사지방 PC에서 외부 CDN이 막혀 있을 수 있음).
// 언어는 C·Python 문법 강조만 등록한다 (언어 서버·자동 완성 워커 없음).
import Editor, { loader } from '@monaco-editor/react'
import * as monaco from 'monaco-editor/editor/editor.api.js'
import 'monaco-editor/languages/definitions/cpp/register.js'
import 'monaco-editor/languages/definitions/python/register.js'
import EditorWorker from 'monaco-editor/editor/editor.worker.js?worker'

self.MonacoEnvironment = { getWorker: () => new EditorWorker() }
loader.config({ monaco })

export interface CodeEditorProps {
  /** 처음 값. 이후에는 에디터가 내용을 들고 있고 onChange로 알린다 */
  defaultValue: string
  language: string
  onChange: (code: string) => void
  readOnly?: boolean
}

export default function CodeEditor({ defaultValue, language, onChange, readOnly }: CodeEditorProps) {
  return (
    <Editor
      height="100%"
      defaultLanguage={language}
      defaultValue={defaultValue}
      onChange={(value) => onChange(value ?? '')}
      loading={<p className="form-hint">에디터 불러오는 중…</p>}
      options={{
        readOnly,
        minimap: { enabled: false },
        fontSize: 14,
        tabSize: 4,
        insertSpaces: true,
        scrollBeyondLastLine: false,
        automaticLayout: true,
        wordWrap: 'on',
      }}
    />
  )
}
