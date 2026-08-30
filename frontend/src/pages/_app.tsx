declare module "*.css" {
  const classes: { [key: string]: string };
  export default classes;
}

import type { AppProps } from "next/app";
import "../styles/globals.css";

export default function App({ Component, pageProps }: AppProps) {
  return <Component {...pageProps} />;
}
