import { apiInitializer } from "discourse/lib/api";
import { mountVestiaire } from "../lib/vestiaire-mount";

export default apiInitializer((api) => {
  const user = api.getCurrentUser();

  api.decorateCookedElement(
    (element, helper) => {
      // posts only: not the composer preview, which re-renders on every keystroke
      if (!helper) return;
      mountVestiaire(element, user ? { username: user.username } : null);
    },
    { id: "vestiaire" }
  );
});
