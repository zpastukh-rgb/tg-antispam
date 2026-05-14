<template>
  <!-- Без Teleport: в TMA при defer + Teleport на #guard-teleport-root слот иногда не монтируется (root 0 children, foundKeys []). -->
  <slot />
</template>
