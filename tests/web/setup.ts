import React from "react";

// Host JSX components can use the classic transform in the Node test loader.
// Scope its React binding to these test processes, as in the host test setup.
Object.defineProperty(globalThis, "React", { value: React, configurable: true });
