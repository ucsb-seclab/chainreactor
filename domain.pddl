(define (domain micronix)
  (:requirements :typing :equality :disjunctive-preconditions)
  (:types
    file data location user group permission process purpose - object
    executable - file
    local remote directory - location
  )

  (:constants
    FS_READ FS_WRITE FS_EXEC - permission
    ; the SHELL string is used to indicate that the file
    ; has been corrupted by the attacker
    SHELL - data
    ; the SYSFILE_PASSWD string is used to indicate that the file
    ; acts like the /etc/passwd file on Linux
    SYSFILE_PASSWD - purpose
  )

  (:predicates
    ; these are the capabilities of the executable
    (CAP_write_file ?e - executable)
    (CAP_read_file ?e - executable)
    (CAP_upload_file ?e - executable)
    (CAP_download_file ?e - executable)
    (CAP_change_permission ?e - executable)
    (CAP_shell ?e - executable)
    (CAP_command ?e - executable)
    (CAP_change_file_owner ?e - executable)

    ; CVE ADDITION - these are the capabilities of the executable vulnerable to the CVE
    (CAP_cve_shell_command_injection ?e - executable)
    (CAP_cve_shell_command_injection_needs_writable_directory ?e - executable ?d - directory)
    (CAP_CVE_write_any_file ?e - executable)
    (CAP_CVE_read_any_file ?e - executable)
    ; whether a user has administator privileges on the system
    (user_is_admin ?u - user)
    ; whether a user is controlled by the attacker. Initially it is the user the attacker has access to.
    (controlled_user ?u - user)

    ; binds a user to a group
    (user_group ?u - user ?g - group)
    ; whether a group has administrator privileges on the system
    (group_is_admin ?g - group)

    ; this represents a running executable. An executable spawns a process that is owned by a user.
    ; in the actions, this predicate is used as token that is generated by the `spawn_process`-like actions
    ; and consumed by the other actions. 
    ; TODO: add also the group of the process
    (process_executable ?p - process ?u - user ?e - executable)

    ;
    ; executables
    ;

    ; the executable is a known binary / script (e.g. /bin/bash)
    (system_executable ?e - executable)
    ; the executable is a custom binary / script
    (user_executable ?e - executable)
    ; the executable as the SUID bit set
    (suid_executable ?e - executable)
    ; when SUID, the process does not drop to nobody:nobody
    (executable_does_not_drop_privileges ?e - executable)
    ; system service (e.g. cron / systemd / rc.d ...)
    (executable_systematically_called_by ?e - executable ?u - user)
    ; the file (a library, a script) is ALWAYS sourced/loaded by some other script / executable (e.g. bashrc, zshrc, .so sideloading...)
    (executable_always_loads_file ?e - executable ?f - file)
    ; the executable loads external files ONLY for specific users
    ; TODO: the data transfer from file to executable should be expressed as an action.
    (executable_loads_user_specific_file ?e - executable ?u - user ?f - file)

    ; data manipulation
    (user_data_in_buffer ?u - user ?d - data) ; the user has some data in stdout, e.g. cat hello.txt puts the contents of hello.txt in the buffer

    ;
    ; files
    ;

    ; the user has ?p permission on the file
    (user_file_permission ?u - user ?f - file ?p - permission)
    ; the group has ?p permission on the file
    (group_file_permission ?g - group ?f - file ?p - permission)
    ; any other user has ?p permission on the file
    (default_file_permission ?f - file ?p - permission)
    ; the file is owned by user:group
    (file_owner ?f - file ?u - user ?g - group)
    ; the file contains ?d data
    (file_contents ?f - file ?d - data)
    ; the file is locates at ?l location (used to indicate local / remote file)
    (file_present_at_location ?f - file ?l - location)
    ; this marks a file with a particular purpose: useful for system files
    ; known to have a specific meaning
    (file_purpose ?f - file ?p - purpose)
    ; this marks a file as a daemon-managed file
    ; these files that handle services on the machine
    ; e.g. systemd/cron/sysv scripts
    ; TODO: as of now we do NOT check which user
    ; is the service running as.
    (daemon_file ?f - file)

    ; directories
    ; the user has ?p permission on the directory
    (user_directory_permission ?u - user ?d - directory ?p - permission)
    ; the group has ?p permission on the directory
    (group_directory_permission ?g - group ?d - directory ?p - permission)
    ; any other user has ?p permission on the directory
    (default_directory_permission ?d - directory ?p - permission)
    ; the directory is owned by user:group
    (directory_owner ?d - directory ?u - user ?g - group)

    ;
    ; composed predicates - generated by actions
    ;

    ; the user can read the file. This is a composed predicate that also takes in account whether a 
    ; user is an administrator, the file is owned by the user, the user has the permission on the file
    ; or the group has the permission on the file
    (user_can_read_file ?u - user ?g - group ?f - file)
    ; similarly, the user can write the file
    (user_can_write_file ?u - user ?g - group ?f - file)
    ; and the user can execute the file
    (user_can_execute_file ?u - user ?g - group ?f - file)
  )

  ;
  ; ACTIONS
  ;

  ; this action is used to propagate the file contents from one file to another
  ; for example, an executable loads a configuration file, and the attacker can control the contents of the file
  (:action propagate_loaded_file_contents
    :parameters (?loaded_file - file ?loader - executable ?d - data)
    :precondition (and
      (executable_always_loads_file ?loader ?loaded_file)
      (file_contents ?loaded_file ?d)
    )
    :effect (and
      (file_contents ?loader ?d)
    )
  )

  ; this action makes an executable SUID
  ; AND it assumes it will not drop privileges  
  (:action make_executable_suid
    :parameters (?pe ?te - executable ?u - user ?g - group ?p - process)
    :precondition (and
      (CAP_change_permission ?pe)
      (process_executable ?p ?u ?pe)

      (or
        (file_owner ?te ?u ?g)
        (user_is_admin ?u)
      )
    )
    :effect (and
      (not (process_executable ?p ?u ?pe))

      (suid_executable ?te)
      (executable_does_not_drop_privileges ?te)
    )
  )

  ; this action changes the owner of a file, if the user running the process is an administrator
  (:action change_file_owner
    :parameters (?f - file ?processUser ?oldUser ?newUser - user ?oldUser_g ?newUser_g ?processUser_g - group ?e - executable ?perm - permission ?p - process)
    :precondition (and
      (user_is_admin ?processUser)

      (CAP_change_file_owner ?e)
      (process_executable ?p ?processUser ?e)
      (user_group ?oldUser ?oldUser_g)
      (user_group ?newUser ?newUser_g)

      (file_owner ?f ?oldUser ?oldUser_g)
    )
    :effect (and
      (not (process_executable ?p ?processUser ?e))

      (not (file_owner ?f ?oldUser ?oldUser_g))
      (file_owner ?f ?newUser ?newUser_g)
    )
  )

  ; this action adds a permission to a file owned by the user spawning the process
  (:action add_permission_of_owned_file
    :parameters (?f - file ?processUser ?u - user ?g - group ?e - executable ?perm - permission ?p - process)
    :precondition (and
      (CAP_change_permission ?e)
      (process_executable ?p ?processUser ?e)

      ; if the user is an administrator,
      ; or the user owns the file,
      ; then they can add any permission
      (or
        (file_owner ?f ?processUser ?g)
        (user_is_admin ?processUser)
      )
    )
    :effect (and
      ; consume the token
      (not (process_executable ?p ?processUser ?e))

      ; arbitrary user "u" has permission "perm" on file "f"
      (user_file_permission ?u ?f ?perm)
    )
  )

  ; this action adds a permission for a specific user
  ; to a directory owned by the user spawning the process
  (:action add_permission_of_owned_directory
    :parameters (?d - directory ?processUser ?u - user ?g - group ?e - executable ?perm - permission ?p - process)
    :precondition (and
      (CAP_change_permission ?e)
      (process_executable ?p ?processUser ?e)
      (user_group ?processUser ?g)

      (or
        (directory_owner ?d ?processUser ?g)
        (user_is_admin ?processUser)
      )
    )
    :effect (and
      ; consume the token
      (not (process_executable ?p ?u ?e))

      ; add permission for user "u" on directory "d"
      (user_directory_permission ?u ?d ?perm)
    )
  )

  ; this action adds a permission for any user on the system
  ; to a file owned by the user spawning the process
  (:action add_default_permission_of_owned_file
    :parameters (?f - file ?u - user ?g - group ?e - executable ?perm - permission ?p - process)
    :precondition (and
      (CAP_change_permission ?e)
      (process_executable ?p ?u ?e)

      (or
        (file_owner ?f ?u ?g)
        (user_is_admin ?u)
      )
    )
    :effect (and
      ; consume the token
      (not (process_executable ?p ?u ?e))

      (default_file_permission ?f ?perm)
    )
  )

  ; this action adds a permission for any user on the system
  ; to a directory owned by the user spawning the process
  (:action add_default_permission_of_owned_directory
    :parameters (?d - directory ?u - user ?g - group ?e - executable ?perm - permission ?p - process)
    :precondition (and
      (user_group ?u ?g)
      (CAP_change_permission ?e)
      (process_executable ?p ?u ?e)

      (or
        (directory_owner ?d ?u ?g)
        (user_is_admin ?u)
      )
    )
    :effect (and
      (not (process_executable ?p ?u ?e))

      (default_directory_permission ?d ?perm)
    )
  )

  ; this is a core action that spawns a process
  ; from an executable that is executable by the
  ; controlled user. the `process_executable` predicate
  ; is used as a token in other actions
  (:action spawn_process
    :parameters (?u - user ?g - group ?e - executable ?p - process)
    :precondition (and
      (controlled_user ?u)
      (user_can_execute_file ?u ?g ?e)
    )
    :effect (and
      (process_executable ?p ?u ?e)
    )
  )

  ; similarly, this action spawns a process from a SUID executable
  ; allowing the attacker to escalate privileges
  (:action spawn_suid_process
    :parameters (?u - user ?su - user ?ug - group ?sug - group ?e - executable ?p - process)
    :precondition (and
      (controlled_user ?u)
      (user_can_execute_file ?u ?ug ?e)

      (suid_executable ?e)
      (executable_does_not_drop_privileges ?e)
      (file_owner ?e ?su ?sug)
    )
    :effect (and
      (process_executable ?p ?su ?e)
    )
  )

  ; this action spawns a process from an executable
  ; that is systematically called by another user
  ; and that has been corrupted by the attacker
  ; by having the SHELL string in its contents
  (:action spawn_injected_shell_from_executable_systematically_called_by_user
    :parameters (?u - user ?other_user - user ?ug - group ?e - executable ?p - process)
    :precondition (and
      (controlled_user ?u)
      (user_can_execute_file ?u ?ug ?e)

      (executable_systematically_called_by ?e ?other_user)
      (file_contents ?e SHELL)
    )
    :effect (and
      (controlled_user ?other_user)
    )
  )

  ; this action spawns a process from an executable
  ; that is systematically called by another user.
  ; in contrast to the previous action, this one
  ; loads a file that is corrupted by the attacker
  ; that is loaded SPECIFICALLY by a user
  ; (i.e not loaded a-priori by the executable)
  (:action spawn_injected_shell_from_corrupted_and_loaded_user_file
    :parameters (?u - user ?other_user - user ?ug - group ?e - executable ?f - file ?p - process)
    :precondition (and
      (controlled_user ?u)
      (user_can_execute_file ?u ?ug ?e)

      (executable_systematically_called_by ?e ?other_user)
      (executable_loads_user_specific_file ?e ?other_user ?f)
      (file_contents ?f SHELL)
    )
    :effect (and
      (controlled_user ?other_user)
    )
  )

  ; having a corrupted service script (always executed on the system)
  ; leads to full system control, assuming we inject a shell
  (:action spawn_injected_shell_from_corrupted_daemon_file
    :parameters (?u - user ?f - file)
    :precondition (and
      (daemon_file ?f)
      (file_contents ?f SHELL)
    )
    :effect (and
      (controlled_user ?u)
    )
  )

  ; this action downloads a file from a remote location
  ; and stores it locally
  (:action download_file
    :parameters (?p - process ?e - executable ?u - user ?g - group ?f - file ?d - data ?local - local ?remote - remote)
    :precondition (and
      (process_executable ?p ?u ?e)
      (CAP_download_file ?e)

      (file_present_at_location ?f ?remote)
    )
    :effect (and
      (not (process_executable ?p ?u ?e))

      (file_present_at_location ?f ?local)
      (file_owner ?f ?u ?g)
    )
  )

  ; this action uploads a file from a local location
  ; to a remote location
  (:action upload_file
    :parameters (?p - process ?e - executable ?f - file ?d - data ?local - local ?remote - remote ?u - user ?g - group)
    :precondition (and
      (process_executable ?p ?u ?e)
      (CAP_upload_file ?e)

      (user_can_read_file ?u ?g ?f)
      (file_present_at_location ?f ?local)
    )
    :effect (and
      (not (process_executable ?p ?u ?e))

      (file_present_at_location ?f ?remote)
    )
  )

  ; this action writes the data from the buffer to a file.
  ; the buffer is filled by the `read_file` action
  ; the buffer can be seen as transient memory
  ; a-la `cat hello.txt | grep "hello"` where the buffer is the pipe
  (:action write_buffer_to_file
    :parameters (?p - process ?e - executable ?f - file ?d - data ?l - local ?u - user ?g - group)
    :precondition (and
      (not (= ?e ?f))
      (CAP_write_file ?e)
      (process_executable ?p ?u ?e)

      (user_can_write_file ?u ?g ?f)
      (user_data_in_buffer ?u ?d)
    )
    :effect (and
      (not (process_executable ?p ?u ?e))

      (file_present_at_location ?f ?l)
      (file_contents ?f ?d)
      (not (user_data_in_buffer ?u ?d))
    )
  )

  ; this action writes arbitrary data to a file
  (:action write_data_to_file
    :parameters (?p - process ?e - executable ?f - file ?d - data ?l - local ?u - user ?g - group)
    :precondition (and
      (not (= ?e ?f))
      (CAP_write_file ?e)
      (process_executable ?p ?u ?e)

      (user_can_write_file ?u ?g ?f)
    )
    :effect (and
      (not (process_executable ?p ?u ?e))

      (file_present_at_location ?f ?l)
      (file_contents ?f ?d)
    )
  )

  ; this action reads the contents of a file
  ; and stores them in the buffer
  ; the buffer can be seen as transient memory
  ; a-la `cat hello.txt | grep "hello"` where the buffer is the pipe
  (:action read_file
    :parameters (?p - process ?e - executable ?f - file ?d - data ?l - local ?u - user ?g - group)
    :precondition (and
      (CAP_read_file ?e)
      (process_executable ?p ?u ?e)

      (user_can_read_file ?u ?g ?f)
      (file_present_at_location ?f ?l)
      (file_contents ?f ?d)
    )
    :effect (and
      (not (process_executable ?p ?u ?e))

      (user_data_in_buffer ?u ?d)
    )
  )

  ; this action spawns a shell from an executable that has the CAP_shell capability
  ; the effect is that we add a new controlled user
  ; to the planning problem
  (:action spawn_shell
    :parameters (?p - process ?e - executable ?u - user)
    :precondition (and
      (CAP_shell ?e)
      (process_executable ?p ?u ?e)
    )
    :effect (and
      (not (process_executable ?p ?u ?e))

      (controlled_user ?u)
    )
  )

  (:action edit_passwd_for_user
    :parameters (?f - file ?u1 - user ?u2 - user ?g - group)
    :precondition (and
      (controlled_user ?u1)
      (user_group ?u1 ?g)
      (file_purpose ?f SYSFILE_PASSWD)
      (user_can_write_file ?u1 ?g ?f)
    )
    :effect (controlled_user ?u2)
  )

  ;
  ; ASSUMPTIONS
  ;
  
  ; this action derives that an executable
  ; with the COMMAND capability can run any command on the system.
  ; to simulate this, we add every possible capability to the executable
  (:action assume_executable_with_cap_command_has_other_capabilities
    :parameters (?e - executable)
    :precondition (and
      (CAP_command ?e)
    )
    :effect (and
      (CAP_write_file ?e)
      (CAP_read_file ?e)
      (CAP_upload_file ?e)
      (CAP_download_file ?e)
      (CAP_change_permission ?e)
    )
  )

  ; this action derives that if a SUID executable
  ; and it's not a known executable,
  ; then it does not drop privileges
  (:action assume_user_executable_does_not_drop_privileges
    :parameters (?e - executable)
    :precondition (and
      (suid_executable ?e)
      (user_executable ?e)
    )
    :effect (executable_does_not_drop_privileges ?e)
  )

  ; this action derived that if a file has
  ; the special SHELL string in its contents,
  ; then it can spawn a shell
  ; the SHELL string signifies that the planner
  ; corrupted the file
  (:action assume_executable_can_spawn_shell
    :parameters (?e - executable)
    :precondition (file_contents ?e SHELL)
    :effect (CAP_shell ?e)
  )

  ; this action derives that a directory owner
  ; has all the permissions on the directory
  (:action assume_directory_permission_from_owner
    :parameters (?u - user ?g - group ?d - directory ?p - permission)
    :precondition (and
      (user_group ?u ?g)
      (directory_owner ?d ?u ?g)
    )
    :effect (user_directory_permission ?u ?d ?p)
  )

  ; this action derives that if a directory
  ; has default permissions, then any user
  ; 
  (:action assume_directory_permission_from_default
    :parameters (?u - user ?d - directory ?p - permission)
    :precondition (default_directory_permission ?d ?p)
    :effect (user_directory_permission ?u ?d ?p)
  )

  ;
  ; AXIOMS
  ;
    
  ; this action derives that if a user in any group they are in
  ; is an administrator, or the group is an administrator,
  ; or they own the file, or they have the permission on the file (user/group)
  ; then they can read the file
  (:action derive_user_can_read_file
    :parameters (?u - user ?g - group ?f - file)
    :precondition (and
      (user_group ?u ?g)

      (or
        (user_is_admin ?u)
        (group_is_admin ?g)
        (file_owner ?f ?u ?g)
        (user_file_permission ?u ?f FS_READ)
        (default_file_permission ?f FS_READ)
        (group_file_permission ?g ?f FS_READ)
      )
    )
    :effect (user_can_read_file ?u ?g ?f)
  )

  ; similarly, this action derives that if a user in any group they are in
  ; is an administrator, or the group is an administrator,
  ; or they own the file, or they have the permission on the file (user/group)
  ; then they can write the file
  (:action derive_user_can_write_file
    :parameters (?u - user ?g - group ?f - file)
    :precondition (and
      (user_group ?u ?g)

      (or
        (user_is_admin ?u)
        (group_is_admin ?g)
        (file_owner ?f ?u ?g)
        (user_file_permission ?u ?f FS_WRITE)
        (default_file_permission ?f FS_WRITE)
        (group_file_permission ?g ?f FS_WRITE)
      )
    )
    :effect (user_can_write_file ?u ?g ?f)
  )

  ; similarly, this action derives that if a user in any group they are in
  ; is an administrator, or the group is an administrator,
  ; or they own the file, or they have the permission on the file (user/group)
  ; then they can execute the file
  (:action derive_user_can_execute_file
    :parameters (?u - user ?g - group ?e - executable)
    :precondition (and
      (user_group ?u ?g)

      (or
        (user_is_admin ?u)
        (group_is_admin ?g)
        (file_owner ?e ?u ?g)
        (system_executable ?e)
        (user_file_permission ?u ?e FS_EXEC)
        (default_file_permission ?e FS_EXEC)
        (group_file_permission ?g ?e FS_EXEC)
      )
    )
    :effect (user_can_execute_file ?u ?g ?e)
  )

  ; CVE ADDITION

  ; this action derives that an executable
  ; with the CVE_SHELL_INJECTION capability can run any command on the system.
  (:action derive_executable_with_cap_cve_shell_command_injection_has_other_capabilities
    :parameters (?e - executable)
    :precondition (and
      (CAP_cve_shell_command_injection ?e)
    )
    ; Consider if we should go directly with CAP_Command
    :effect (CAP_command ?e)
  )

  (:action check_cve_shell_command_injection_needs_writable_directory
    :parameters (?e - executable ?d - directory ?u - user )
    :precondition (and 
      (CAP_cve_shell_command_injection_needs_writable_directory ?e ?d)
      (user_directory_permission ?d ?u FS_WRITE)
    )
    :effect (CAP_cve_shell_command_injection ?e    
    )
  )

  (:action derive_user_can_read_anything_from_executable_with_CAP_CVE_read_any_file
    :parameters (?e - executable ?u - user ?g - group ?f - file ?p - process)
    :precondition (and
      (CAP_CVE_read_any_file ?e)
      (process_executable ?p ?u ?e)
      (controlled_user ?u)
      (user_group ?u ?g)
    )
    :effect (user_can_read_file ?u ?g ?f)
  )

  (:action write_data_to_file_using_executable_with_CAP_CVE_write_any_file
    :parameters (?p - process ?e - executable ?f - file ?d - data ?l - local ?u - user ?g - group)
    :precondition (and
      (not (= ?e ?f))
      (CAP_CVE_write_any_file ?e)
      (process_executable ?p ?u ?e)
      (controlled_user ?u)
      (user_group ?u ?g)
    )
    :effect (and
      (not (process_executable ?p ?u ?e))
      (file_contents ?f ?d)
    )
  )
)