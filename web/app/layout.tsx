import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "GCP Infra Review",
  description:
    "Review Terraform for Google Cloud before you apply it: security, monthly cost and cheaper alternatives.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
