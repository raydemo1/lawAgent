/**
 * Global `JSX` namespace shim for React 19 type definitions.
 *
 * Background: `@types/react` v19 moved the `JSX` namespace behind the `react`
 * module (`import type { JSX } from 'react'`) and no longer declares a global
 * `JSX` namespace. Several modules in this app annotate component return types
 * as `JSX.Element` without importing the namespace, which relies on the global
 * `JSX` namespace that existed under `@types/react` v18.
 *
 * This ambient declaration restores a global `JSX` namespace that simply
 * aliases React 19's `JSX` namespace, so those existing annotations keep
 * type-checking without editing every module. New code is still free to use
 * `import type { JSX } from 'react'` directly.
 *
 * Note: JSX *expression* type-checking (intrinsic elements etc.) is handled by
 * the automatic runtime (`jsx: "react-jsx"`) via the `react` module's own
 * `JSX` namespace, so this global alias is only consulted for explicit
 * `JSX.*` type references.
 */
import type { JSX as ReactJSX } from 'react';

declare global {
  namespace JSX {
    type ElementType = ReactJSX.ElementType;
    type Element = ReactJSX.Element;
    type ElementClass = ReactJSX.ElementClass;
    type ElementAttributesProperty = ReactJSX.ElementAttributesProperty;
    type ElementChildrenAttribute = ReactJSX.ElementChildrenAttribute;
    type LibraryManagedAttributes<C, P> = ReactJSX.LibraryManagedAttributes<C, P>;
    type IntrinsicAttributes = ReactJSX.IntrinsicAttributes;
    type IntrinsicClassAttributes<T> = ReactJSX.IntrinsicClassAttributes<T>;
    type IntrinsicElements = ReactJSX.IntrinsicElements;
  }
}

// Ensure this file is treated as a module (it has an import above), so the
// `declare global` augmentation takes effect.
export {};
