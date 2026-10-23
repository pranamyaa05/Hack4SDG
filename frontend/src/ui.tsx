import { cloneElement, isValidElement, useId, type ReactNode } from "react";
export function Field({
  label,
  children,
  hint,
}: {
  label: string;
  children: ReactNode;
  hint?: string;
}) {
  const id = useId();
  const control =
    isValidElement<{ id?: string; "aria-describedby"?: string }>(children) &&
    typeof children.type === "string" &&
    ["input", "select", "textarea"].includes(children.type);
  return (
    <div className="field">
      {control ? <label htmlFor={id}>{label}</label> : <span>{label}</span>}
      {control
        ? cloneElement(children, {
            id,
            "aria-describedby": hint ? id + "-hint" : undefined,
          })
        : children}
      {hint && <small id={id + "-hint"}>{hint}</small>}
    </div>
  );
}
export function Badge({ children }: { children: ReactNode }) {
  return <span className="badge">{children}</span>;
}
