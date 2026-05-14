import { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { oneLight } from "react-syntax-highlighter/dist/esm/styles/prism";
import { Check, Copy } from "lucide-react";
import type { Components } from "react-markdown";

function CodeBlock({ language, code }: { language: string; code: string }) {
  const [copied, setCopied] = useState(false);

  function handleCopy() {
    navigator.clipboard.writeText(code).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  }

  return (
    <div className="relative my-3 overflow-hidden rounded-xl border border-kibo-border">
      <div className="flex items-center justify-between border-b border-kibo-border bg-kibo-surface px-4 py-2">
        <span className="font-mono text-xs text-kibo-dim">{language || "code"}</span>
        <button
          type="button"
          onClick={handleCopy}
          className="flex items-center gap-1.5 rounded-md px-2 py-1 text-xs text-kibo-dim transition-all hover:bg-kibo-border hover:text-kibo-text"
        >
          {copied ? <Check size={12} /> : <Copy size={12} />}
          {copied ? "Copied" : "Copy"}
        </button>
      </div>
      <SyntaxHighlighter
        language={language || "text"}
        style={oneLight}
        customStyle={{
          margin: 0,
          padding: "16px",
          background: "transparent",
          fontSize: "0.85rem",
          lineHeight: "1.65",
        }}
        PreTag="div"
      >
        {code}
      </SyntaxHighlighter>
    </div>
  );
}

const markdownComponents: Components = {
  pre({ children }) {
    return <>{children}</>;
  },
  code({ className, children }) {
    const match = /language-(\w+)/.exec(className || "");
    if (match) {
      return (
        <CodeBlock
          language={match[1]}
          code={String(children).replace(/\n$/, "")}
        />
      );
    }
    return (
      <code className="rounded-md border border-kibo-border bg-kibo-surface px-1.5 py-0.5 font-mono text-[0.82em] text-kibo-text">
        {children}
      </code>
    );
  },
  h1({ children }) {
    return (
      <h1 className="mb-3 mt-5 border-b border-kibo-border pb-1 text-[1.05rem] font-semibold text-kibo-text first:mt-0">
        {children}
      </h1>
    );
  },
  h2({ children }) {
    return (
      <h2 className="mb-2 mt-4 text-base font-semibold text-kibo-text first:mt-0">
        {children}
      </h2>
    );
  },
  h3({ children }) {
    return (
      <h3 className="mb-2 mt-3 text-sm font-semibold text-kibo-text first:mt-0">
        {children}
      </h3>
    );
  },
  p({ children }) {
    return <p className="mb-3 leading-relaxed last:mb-0">{children}</p>;
  },
  ul({ children }) {
    return <ul className="mb-3 list-disc space-y-1 pl-5 last:mb-0">{children}</ul>;
  },
  ol({ children }) {
    return <ol className="mb-3 list-decimal space-y-1 pl-5 last:mb-0">{children}</ol>;
  },
  li({ children }) {
    return <li className="leading-relaxed">{children}</li>;
  },
  blockquote({ children }) {
    return (
      <blockquote className="my-3 border-l-2 border-kibo-accent pl-4 italic text-kibo-dim">
        {children}
      </blockquote>
    );
  },
  table({ children }) {
    return (
      <div className="my-3 overflow-x-auto rounded-lg border border-kibo-border">
        <table className="w-full text-sm">{children}</table>
      </div>
    );
  },
  thead({ children }) {
    return <thead className="bg-kibo-surface">{children}</thead>;
  },
  th({ children }) {
    return (
      <th className="border-b border-kibo-border px-4 py-2 text-left font-semibold text-kibo-text">
        {children}
      </th>
    );
  },
  td({ children }) {
    return (
      <td className="border-b border-kibo-border px-4 py-2 text-kibo-text last:border-b-0">
        {children}
      </td>
    );
  },
  tr({ children }) {
    return <tr className="even:bg-kibo-surface/50">{children}</tr>;
  },
  a({ href, children }) {
    return (
      <a
        href={href}
        onClick={(e) => {
          e.preventDefault();
          if (href) window.open(href, "_blank");
        }}
        className="text-kibo-accent underline decoration-kibo-accent/40 transition-all hover:decoration-kibo-accent"
      >
        {children}
      </a>
    );
  },
  strong({ children }) {
    return <strong className="font-semibold text-kibo-text">{children}</strong>;
  },
  hr() {
    return <hr className="my-4 border-kibo-border" />;
  },
};

export function MarkdownContent({ text }: { text: string }) {
  return (
    <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
      {text}
    </ReactMarkdown>
  );
}
