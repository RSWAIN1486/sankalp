function parseNodeVersion(version) {
  const [majorStr, minorStr] = version.split(".");
  return {
    major: Number(majorStr || 0),
    minor: Number(minorStr || 0)
  };
}

function satisfiesViteNodeRequirement(version) {
  const { major, minor } = parseNodeVersion(version);
  if (major > 22) return true;
  if (major === 22) return minor >= 12;
  if (major === 20) return minor >= 19;
  return false;
}

const current = process.versions.node;

if (!satisfiesViteNodeRequirement(current)) {
  console.error("");
  console.error("Sankalp WebUI requires Node.js 20.19+ or 22.12+.");
  console.error(`Current Node.js version: ${current}`);
  console.error("");
  console.error("Fix:");
  console.error("  cd /Users/rswai/sankalp/web");
  console.error("  source ~/.nvm/nvm.sh");
  console.error("  nvm use   # uses .nvmrc (24)");
  console.error("");
  process.exit(1);
}
