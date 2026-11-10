"use client";

import type { ReviewOptions } from "@/lib/types";

export type Advanced = { model: string; searchDocs: boolean; extraInstructions: string };

export const DEFAULT_ADVANCED: Advanced = { model: "", searchDocs: true, extraInstructions: "" };

/** Only the settings that differ from the defaults are sent, so the server keeps its own. */
export function toOptions(advanced: Advanced): ReviewOptions {
  const options: ReviewOptions = {};
  if (advanced.model.trim()) options.model = advanced.model.trim();
  if (!advanced.searchDocs) options.use_rag = false;
  if (advanced.extraInstructions.trim()) {
    options.extra_instructions = advanced.extraInstructions.trim();
  }
  return options;
}

/**
 * Settings most people never need, kept out of the main flow. None of them can change a
 * security finding: the rules do not read them.
 */
export function AdvancedSettings({
  value,
  defaultModel,
  onChange,
}: {
  value: Advanced;
  defaultModel: string;
  onChange: (value: Advanced) => void;
}) {
  return (
    <details>
      <summary>Advanced settings</summary>
      <fieldset>
        <legend>Advanced settings</legend>
        <p className="muted">
          For trying other AI models. These do not change the security rules or their findings.
        </p>
        <label>
          AI model (empty = {defaultModel})
          <input
            type="text"
            maxLength={100}
            placeholder={defaultModel}
            value={value.model}
            onChange={(event) => onChange({ ...value, model: event.target.value })}
          />
        </label>
        <label className="check">
          <input
            type="checkbox"
            checked={value.searchDocs}
            onChange={(event) => onChange({ ...value, searchDocs: event.target.checked })}
          />{" "}
          Search the documentation before writing suggestions
        </label>
        <label>
          Extra instructions for the report writer
          <textarea
            rows={2}
            maxLength={1000}
            value={value.extraInstructions}
            onChange={(event) => onChange({ ...value, extraInstructions: event.target.value })}
          />
        </label>
      </fieldset>
    </details>
  );
}
