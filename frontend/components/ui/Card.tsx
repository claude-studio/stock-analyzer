interface CardProps {
  title?: string;
  children: React.ReactNode;
  className?: string;
}

export function Card({ title, children, className }: CardProps) {
  return (
    <div
      className={`rounded-lg border border-gray-800 bg-gray-900 p-4 ${className || ""}`}
    >
      {title && (
        <h3 className="text-sm font-medium text-gray-400 mb-3">{title}</h3>
      )}
      {children}
    </div>
  );
}
