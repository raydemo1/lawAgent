import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeRaw from "rehype-raw";

interface MarkdownTextProps {
  children: string;
  variant?: "report" | "inline" | "note";
  className?: string;
}

export default function MarkdownText({
  children,
  variant = "report",
  className,
}: MarkdownTextProps) {
  return (
    <div className={`markdown-body markdown-body--${variant} ${className || ""}`}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[rehypeRaw]}
        components={{
          sup: ({ node, ...props }) => (
            <sup {...props} />
          ),
        }}
      >
        {children}
      </ReactMarkdown>
    </div>
  );
}
