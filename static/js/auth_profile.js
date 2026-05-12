function togglePassword(id){
  const input = document.getElementById(id);
  if(!input) return;
  input.type = input.type === "password" ? "text" : "password";
}
