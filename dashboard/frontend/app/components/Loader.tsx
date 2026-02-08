export default function Loader({
  size = "medium",
  text,
  centered = false,
}: {
  size?: "small" | "medium" | "large";
  text?: string;
  centered?: boolean;
}) {
  const sizeClass =
    size === "small" ? "w-4 h-4" : size === "large" ? "w-12 h-12" : "w-8 h-8";

  const wrapperClass = centered
    ? "flex flex-col items-center justify-center p-8 w-full"
    : "flex flex-col items-center inline-flex";

  return (
    <div className={wrapperClass}>
      <div className={`spinner ${size}`}></div>
      {text && <p className="mt-3 text-muted text-sm animate-pulse">{text}</p>}
    </div>
  );
}
