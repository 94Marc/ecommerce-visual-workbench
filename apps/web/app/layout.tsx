import type { Metadata } from "next";

import "./globals.css";

export const metadata: Metadata = {
  title: "Frameflow · 跨境商品视觉工作台",
  description: "将供应商素材生产为平台合规商品图片",
};

export default function RootLayout({children}: Readonly<{children: React.ReactNode}>) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
