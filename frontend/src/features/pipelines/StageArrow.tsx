/** Connector drawn between two consecutive stages. */
export function StageArrow() {
  return (
    <div className="flex flex-col items-center py-2" aria-hidden="true">
      <span className="h-6 w-px bg-gradient-to-b from-sky-400/0 via-sky-400/60 to-indigo-400/60" />
      <span className="border-x-[5px] border-t-[6px] border-x-transparent border-t-indigo-400/70" />
    </div>
  );
}
