import { UTILITIES } from "../utilities";

export default function UtilityCards({ selectedId, onSelect, disabled }) {
  return (
    <nav className="cards" aria-label="Choose a study tool">
      {UTILITIES.map((u) => (
        <button key={u.id} type="button" className={`card ${u.id === selectedId ? "selected" : ""}`}
          onClick={() => onSelect(u.id)} disabled={disabled} aria-pressed={u.id === selectedId}>
          <span className="card-icon" aria-hidden="true">{u.icon}</span>
          <span className="card-name">{u.name}</span>
          <span className="card-text">{u.cardText}</span>
        </button>
      ))}
    </nav>
  );
}
