// Minimal test-only surface used from the host's existing jsdom dependency.
declare module "jsdom" {
  export class JSDOM {
    constructor(html: string, options: { url: string });
    window: Window & typeof globalThis;
  }
}
