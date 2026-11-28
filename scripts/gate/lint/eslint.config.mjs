// Rules of the structure ratchet only; style is not judged here. Limits arrive as --rule flags.
const NESTED = ":function:not(CallExpression > .callee)";

export default [
  {
    files: ["**/*.js", "**/*.mjs", "**/*.cjs", "**/*.jsx"],
    languageOptions: { ecmaVersion: "latest", parserOptions: { ecmaFeatures: { jsx: true } } },
    rules: {
      "no-restricted-syntax": [
        "error",
        { selector: `${NESTED} FunctionDeclaration`, message: "Named function declared inside a function." },
        { selector: `${NESTED} VariableDeclarator > :function.init`, message: "Named function inside a function." },
      ],
    },
  },
];
