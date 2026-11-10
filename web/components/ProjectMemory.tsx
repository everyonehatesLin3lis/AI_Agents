"use client";

import { useEffect, useState } from "react";

import { getMemory, saveMemory } from "@/lib/api";
import { REGIONS } from "@/lib/labels";

/** What the tool remembers about one project and uses in every later review of it. */
export function ProjectMemory({ project }: { project: string }) {
  const [budget, setBudget] = useState("");
  const [region, setRegion] = useState("");
  const [preferences, setPreferences] = useState("");
  const [status, setStatus] = useState("");

  useEffect(() => {
    let current = true;
    getMemory(project)
      .then((memory) => {
        if (!current) return;
        setBudget(memory.budget_monthly_usd === null ? "" : String(memory.budget_monthly_usd));
        setRegion(memory.region ?? "");
        setPreferences(memory.preferences.join("\n"));
        setStatus("");
      })
      .catch(() => current && setStatus("Could not load this project's memory."));
    return () => {
      current = false;
    };
  }, [project]);

  const save = async (event: React.FormEvent) => {
    event.preventDefault();
    try {
      await saveMemory(project, {
        budget_monthly_usd: budget.trim() ? Number(budget) : null,
        region: region || null,
        preferences: preferences
          .split("\n")
          .map((line) => line.trim())
          .filter(Boolean),
      });
      setStatus("Saved.");
    } catch {
      setStatus("Could not save. Is the Python API running?");
    }
  };

  return (
    <form onSubmit={save}>
      <fieldset>
        <legend>Project memory</legend>
        <p className="muted">
          Remembered for the project “{project}” and used in every review of it. A budget adds a
          finding when the estimate is above it.
        </p>
        <label>
          Monthly budget in USD (empty = none)
          <input
            type="number"
            min="0"
            step="1"
            value={budget}
            onChange={(event) => setBudget(event.target.value)}
          />
        </label>
        <label>
          Default region
          <select value={region} onChange={(event) => setRegion(event.target.value)}>
            <option value="">(not set)</option>
            {REGIONS.map((name) => (
              <option key={name} value={name}>
                {name}
              </option>
            ))}
          </select>
        </label>
        <label>
          Preferences, one per line
          <textarea
            rows={3}
            maxLength={500}
            value={preferences}
            onChange={(event) => setPreferences(event.target.value)}
          />
        </label>
        <button type="submit">Save</button>
        {status && (
          <p role="status" className="muted">
            {status}
          </p>
        )}
      </fieldset>
    </form>
  );
}
