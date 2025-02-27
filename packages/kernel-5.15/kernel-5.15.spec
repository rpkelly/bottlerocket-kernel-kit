%global debug_package %{nil}

Name: %{_cross_os}kernel-5.15
Version: 5.15.178
Release: 1%{?dist}
Summary: The Linux kernel
License: GPL-2.0 WITH Linux-syscall-note
URL: https://www.kernel.org/
# Use latest-kernel-srpm-url.sh to get this.
Source0: https://cdn.amazonlinux.com/blobstore/54de66dab22b2c48ec0f7771a6561caca6d72acca4765533d5d0936c9be05b18/kernel-5.15.178-120.178.amzn2.src.rpm
Source1: gpgkey-99E617FE5DB527C0D8BD5F8E11CF1F95C87F5B1A.asc
# Use latest-neuron-srpm-url.sh to get this.
Source2: https://yum.repos.neuron.amazonaws.com/aws-neuronx-dkms-2.19.64.0.noarch.rpm
Source3: gpgkey-00FA2C1079260870A76D2C285749CAD8646D9185.asc
Source100: config-bottlerocket

# Neuron-related drop-ins.
Source220: neuron-sysinit.target.drop-in.conf
Source221: modprobe@neuron.service.drop-in.conf

# Help out-of-tree module builds run `make prepare` automatically.
Patch1001: 1001-Makefile-add-prepare-target-for-external-modules.patch
# Expose tools/* targets for out-of-tree module builds.
Patch1002: 1002-Revert-kbuild-hide-tools-build-targets-from-external.patch
# Enable INITRAMFS_FORCE config option for our use case.
Patch1003: 1003-initramfs-unlink-INITRAMFS_FORCE-from-CMDLINE_-EXTEN.patch
# Increase default of sysctl net.unix.max_dgram_qlen to 512.
Patch1004: 1004-af_unix-increase-default-max_dgram_qlen-to-512.patch

BuildRequires: bc
BuildRequires: elfutils-devel
BuildRequires: hostname
BuildRequires: kmod
BuildRequires: openssl-devel

# CPU microcode updates are included as "extra firmware" so the files don't
# need to be installed on the root filesystem. However, we want the license and
# attribution files to be available in the usual place.
%if "%{_cross_arch}" == "x86_64"
BuildRequires: %{_cross_os}microcode
Requires: %{_cross_os}microcode-licenses
%endif

# Pull in expected modules and development files.
Requires: %{name}-modules = %{version}-%{release}
Requires: %{name}-devel = %{version}-%{release}

# Pull in platform-dependent modules.
%if "%{_cross_arch}" == "x86_64"
Requires: (%{name}-modules-neuron if (%{_cross_os}variant-platform(aws) without %{_cross_os}variant-flavor(nvidia)))
%endif

# The 5.15 kernel is not FIPS certified.
Conflicts: %{_cross_os}image-feature(fips)

# Using EROFS for the root partition requires a 6.1+ kernel.
Conflicts: %{_cross_os}image-feature(erofs-root-partition)

%global kernel_sourcedir %{_cross_usrsrc}/kernels
%global kernel_libdir %{_cross_libdir}/modules/%{version}

%description
%{summary}.

%package devel
Summary: Configured Linux kernel source for module building

%description devel
%{summary}.

%package archive
Summary: Archived Linux kernel source for module building

%description archive
%{summary}.

%package modules
Summary: Modules for the Linux kernel

%description modules
%{summary}.

%if "%{_cross_arch}" == "x86_64"
%package modules-neuron
Summary: Modules for the Linux kernel with Neuron hardware
Requires: %{name}
Requires: %{_cross_os}ghostdog
Requires: %{_cross_os}variant-platform(aws)
Conflicts: %{_cross_os}variant-flavor(nvidia)

%description modules-neuron
%{summary}.
%endif

%package headers
Summary: Header files for the Linux kernel for use by glibc

%description headers
%{summary}.

%prep
rpmkeys --import %{S:1} --dbpath "${PWD}/rpmdb"
rpmkeys --checksig %{S:0} --dbpath "${PWD}/rpmdb"
rm -rf "${PWD}/rpmdb"
rpm2cpio %{S:0} | cpio -iu {,./}linux-%{version}.tar {,./}config-%{_cross_arch} {,./}"*.patch" {,./}kernel.spec
tar -xof linux-%{version}.tar; rm linux-%{version}.tar
# Count all the patches extracted from the SRPM
patches_count=$(find -name "*.patch" | wc -l)
# Find patch ordering based on the Source0 kernel.spec file from the SRPM.
# First, find all `PatchNNN` lines. Then, sort by the patch number (-k1.6 in sort sets the 6th char
# in field 1 of input as the sort parameter). Finally, capture just the patch file name specified.
readarray -t patches < <(grep -P "^Patch\d+" kernel.spec | sort -n -k1.6 | grep -oP "^Patch\d+: \K.*\.patch$" kernel.spec)
# Fail the build if there is a mismatch in the number of patches found
if [[ "${patches_count}" -ne "${#patches[@]}" ]]; then
  echo "Mismatch on patches count!"
  exit 1
fi

%setup -TDn linux-%{version}
# Patches from the Source0 SRPM
for patch in ${patches[@]}; do
    patch -p1 <../"$patch"
done
# Patches listed in this spec (Patch0001...)
%autopatch -p1

%if "%{_cross_arch}" == "x86_64"
microcode="$(find %{_cross_libdir}/firmware -type f -path '*/*-ucode/*' -printf '%%P\n' | sort | tr '\n' ' ')"
cat <<EOF > ../config-microcode
CONFIG_EXTRA_FIRMWARE="${microcode}"
CONFIG_EXTRA_FIRMWARE_DIR="%{_cross_libdir}/firmware"
EOF
%endif

export ARCH="%{_cross_karch}"
export CROSS_COMPILE="%{_cross_target}-"

KCONFIG_CONFIG="arch/%{_cross_karch}/configs/%{_cross_vendor}_defconfig" \
scripts/kconfig/merge_config.sh \
  ../config-%{_cross_arch} \
%if "%{_cross_arch}" == "x86_64"
  ../config-microcode \
%endif
  %{S:100}

rm -f ../config-* ../*.patch

%if "%{_cross_arch}" == "x86_64"
cd %{_builddir}
rpmkeys --import %{S:3} --dbpath "${PWD}/rpmdb"
rpmkeys --checksig %{S:2} --dbpath "${PWD}/rpmdb"
rm -rf "${PWD}/rpmdb"
rpm2cpio %{S:2} | cpio -idmu './usr/src/aws-neuronx-*'
find usr/src/ -mindepth 1 -maxdepth 1 -type d -exec mv {} neuron \;
rm -r usr
%endif

%global kmake \
make -s\\\
  ARCH="%{_cross_karch}"\\\
  CROSS_COMPILE="%{_cross_target}-"\\\
  INSTALL_HDR_PATH="%{buildroot}%{_cross_prefix}"\\\
  INSTALL_MOD_PATH="%{buildroot}%{_cross_prefix}"\\\
  INSTALL_MOD_STRIP=1\\\
%{nil}

%build
%kmake mrproper
%kmake %{_cross_vendor}_defconfig
%kmake %{?_smp_mflags} %{_cross_kimage}
%kmake %{?_smp_mflags} modules

%if "%{_cross_arch}" == "x86_64"
%kmake %{?_smp_mflags} M=%{_builddir}/neuron
%endif

%install
%kmake %{?_smp_mflags} headers_install
%kmake %{?_smp_mflags} modules_install

%if "%{_cross_arch}" == "x86_64"
%kmake %{?_smp_mflags} M=%{_builddir}/neuron modules_install
%endif

install -d %{buildroot}/boot
install -T -m 0755 arch/%{_cross_karch}/boot/%{_cross_kimage} %{buildroot}/boot/vmlinuz
install -m 0644 .config %{buildroot}/boot/config

find %{buildroot}%{_cross_prefix} \
   \( -name .install -o -name .check -o \
      -name ..install.cmd -o -name ..check.cmd \) -delete

# For out-of-tree kmod builds, we need to support the following targets:
#   make scripts -> make prepare -> make modules
#
# This requires enough of the kernel tree to build host programs under the
# "scripts" and "tools" directories.

# Any existing ELF objects will not work properly if we're cross-compiling for
# a different architecture, so get rid of them to avoid confusing errors.
find arch scripts tools -type f -executable \
  -exec sh -c "head -c4 {} | grep -q ELF && rm {}" \;

# We don't need to include these files.
find -type f \( -name \*.cmd -o -name \*.gitignore \) -delete

# Avoid an OpenSSL dependency by stubbing out options for module signing and
# trusted keyrings, so `sign-file` and `extract-cert` won't be built. External
# kernel modules do not have access to the keys they would need to make use of
# these tools.
sed -i \
  -e 's,$(CONFIG_MODULE_SIG_FORMAT),n,g' \
  -e 's,$(CONFIG_SYSTEM_TRUSTED_KEYRING),n,g' \
  scripts/Makefile

# Restrict permissions on System.map.
chmod 600 System.map

(
  find * \
    -type f \
    \( -name Build\* -o -name Kbuild\* -o -name Kconfig\* -o -name Makefile\* \) \
    -print

  find arch/%{_cross_karch}/ \
    -type f \
    \( -name module.lds -o -name vmlinux.lds.S -o -name Platform -o -name \*.tbl \) \
    -print

  find arch/%{_cross_karch}/{include,lib}/ -type f ! -name \*.o ! -name \*.o.d -print
  echo arch/%{_cross_karch}/kernel/asm-offsets.s
  echo lib/vdso/gettimeofday.c

  for d in \
    arch/%{_cross_karch}/tools \
    arch/%{_cross_karch}/kernel/vdso ; do
    [ -d "${d}" ] && find "${d}/" -type f -print
  done

  find include -type f -print
  find scripts -type f ! -name \*.l ! -name \*.y ! -name \*.o -print

  find tools/{arch/%{_cross_karch},include,objtool,scripts}/ -type f ! -name \*.o -print
  echo tools/build/fixdep.c
  find tools/lib/subcmd -type f -print
  find tools/lib/{ctype,hweight,rbtree,string,str_error_r}.c

  echo kernel/bounds.c
  echo kernel/time/timeconst.bc
  echo security/selinux/include/classmap.h
  echo security/selinux/include/initial_sid_to_string.h
  echo security/selinux/include/policycap.h
  echo security/selinux/include/policycap_names.h

  echo .config
  echo Module.symvers
  echo System.map
) | sort -u > kernel_devel_files

# Create squashfs of kernel-devel files (ie. /usr/src/kernels/<version>).
#
# -no-exports:
# The filesystem does not need to be exported via NFS.
#
# -all-root:
# Make all files owned by root rather than the build user.
#
# -comp zstd:
# zstd offers compression ratios like xz and decompression speeds like lz4.
SQUASHFS_OPTS="-no-exports -all-root -comp zstd"
mkdir -p src_squashfs/%{version}
tar c -T kernel_devel_files | tar x -C src_squashfs/%{version}
mksquashfs src_squashfs kernel-devel.squashfs ${SQUASHFS_OPTS}

# Create a tarball of the same files, for use outside the running system.
# In theory we could extract these files with `unsquashfs`, but we do not want
# to require it to be installed on the build host, and it errors out when run
# inside Docker unless the limit for open files is lowered.
tar cf kernel-devel.tar src_squashfs/%{version} --transform='s|src_squashfs/%{version}|kernel-devel|'
xz -T0 kernel-devel.tar

install -D kernel-devel.squashfs %{buildroot}%{_cross_datadir}/bottlerocket/kernel-devel.squashfs
install -D kernel-devel.tar.xz %{buildroot}%{_cross_datadir}/bottlerocket/kernel-devel.tar.xz
install -d %{buildroot}%{kernel_sourcedir}

# Replace the incorrect links from modules_install. These will be bound
# into a host container (and unused in the host) so they must not point
# to %{_cross_usrsrc} (eg. /x86_64-bottlerocket-linux-gnu/sys-root/...)
rm -f %{buildroot}%{kernel_libdir}/build %{buildroot}%{kernel_libdir}/source
ln -sf %{_usrsrc}/kernels/%{version} %{buildroot}%{kernel_libdir}/build
ln -sf %{_usrsrc}/kernels/%{version} %{buildroot}%{kernel_libdir}/source

# Install a copy of System.map so that module dependencies can be regenerated.
install -p -m 0600 System.map %{buildroot}%{kernel_libdir}

%if "%{_cross_arch}" == "x86_64"
# Add Neuron-related drop-ins to load the module when the hardware is present.
mkdir -p %{buildroot}%{_cross_unitdir}/sysinit.target.d
install -p -m 0644 %{S:220} %{buildroot}%{_cross_unitdir}/sysinit.target.d/neuron.conf

mkdir -p %{buildroot}%{_cross_unitdir}/modprobe@neuron.service.d
install -p -m 0644 %{S:221} %{buildroot}%{_cross_unitdir}/modprobe@neuron.service.d/neuron.conf
%endif

%files
%license COPYING LICENSES/preferred/GPL-2.0 LICENSES/exceptions/Linux-syscall-note
%{_cross_attribution_file}
/boot/vmlinuz
/boot/config

%files modules
%dir %{_cross_libdir}/modules
%{_cross_libdir}/modules/*
%exclude %{kernel_libdir}/extra/neuron.ko.gz

%if "%{_cross_arch}" == "x86_64"
%files modules-neuron
%{kernel_libdir}/extra/neuron.ko.gz
%{_cross_unitdir}/sysinit.target.d/neuron.conf
%{_cross_unitdir}/modprobe@neuron.service.d/neuron.conf
%endif

%files headers
%dir %{_cross_includedir}/asm
%dir %{_cross_includedir}/asm-generic
%dir %{_cross_includedir}/drm
%dir %{_cross_includedir}/linux
%dir %{_cross_includedir}/misc
%dir %{_cross_includedir}/mtd
%dir %{_cross_includedir}/rdma
%dir %{_cross_includedir}/scsi
%dir %{_cross_includedir}/sound
%dir %{_cross_includedir}/video
%dir %{_cross_includedir}/xen
%{_cross_includedir}/asm/*
%{_cross_includedir}/asm-generic/*
%{_cross_includedir}/drm/*
%{_cross_includedir}/linux/*
%{_cross_includedir}/misc/*
%{_cross_includedir}/mtd/*
%{_cross_includedir}/rdma/*
%{_cross_includedir}/scsi/*
%{_cross_includedir}/sound/*
%{_cross_includedir}/video/*
%{_cross_includedir}/xen/*

%files devel
%dir %{kernel_sourcedir}
%{_cross_datadir}/bottlerocket/kernel-devel.squashfs

%files archive
%{_cross_datadir}/bottlerocket/kernel-devel.tar.xz

%changelog
